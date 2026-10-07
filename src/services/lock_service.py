from __future__ import annotations

import json
import logging
import math
import os
import sys
import time
import errno
import ctypes
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
DEFAULT_LOCK_TTL_SECONDS = 7200.0


def _owner_pid_is_alive(pid: int) -> bool:
    """Return whether a local lock owner is still running.

    Repository locks are local filesystem coordination primitives. A process
    terminated after lock acquisition must not hold a workflow until a long TTL
    expires. Permission failures remain conservative and retain the lock.
    """
    if pid <= 0:
        return False
    if sys.platform == "win32":
        # Windows does not support signal zero as a process-existence check.
        # Query-limited access succeeds for a running local owner and lets us
        # keep access-denied owners conservative without retaining a dead PID.
        kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
        handle = kernel32.OpenProcess(0x1000, False, pid)
        if handle:
            exit_code = ctypes.c_ulong()
            try:
                if not kernel32.GetExitCodeProcess(handle, ctypes.byref(exit_code)):
                    return True
                return exit_code.value == 259  # STILL_ACTIVE
            finally:
                kernel32.CloseHandle(handle)
        return ctypes.get_last_error() not in {87, 1168}
    try:
        os.kill(pid, 0)
    except ProcessLookupError:
        return False
    except PermissionError:
        return True
    except OSError as exc:
        if exc.errno == errno.ESRCH:
            return False
        return True
    return True


def _read_lock(path: str) -> Optional[LockInfo]:
    file_path = Path(path)
    try:
        raw_payload = file_path.read_text(encoding="utf-8")
    except FileNotFoundError:
        return None
    except UnicodeDecodeError as exc:
        raise _corrupt_lock_error(path, "invalid_encoding", cause=exc) from exc
    except OSError as exc:
        raise AppError(
            code="lock_file_read_failed",
            message="Failed to read the existing lock file",
            cause=exc,
            retryable=False,
            context={"lock_path": path},
        ) from exc
    try:
        data = json.loads(raw_payload)
    except json.JSONDecodeError as exc:
        raise _corrupt_lock_error(path, "invalid_json", cause=exc) from exc
    if not isinstance(data, dict):
        raise _corrupt_lock_error(path, "invalid_payload_shape")

    owner_id = data.get("owner_id")
    pid = data.get("pid")
    created_at = data.get("created_at")
    ttl_seconds = data.get("ttl_seconds", DEFAULT_LOCK_TTL_SECONDS)
    if not isinstance(owner_id, str) or not owner_id.strip():
        raise _corrupt_lock_error(path, "invalid_owner_id")
    if type(pid) is not int or pid <= 0:
        raise _corrupt_lock_error(path, "invalid_pid")
    if (
        isinstance(created_at, bool)
        or not isinstance(created_at, (int, float))
        or not math.isfinite(created_at)
        or created_at < 0
    ):
        raise _corrupt_lock_error(path, "invalid_created_at")
    if (
        isinstance(ttl_seconds, bool)
        or not isinstance(ttl_seconds, (int, float))
        or not math.isfinite(ttl_seconds)
        or ttl_seconds < 0
    ):
        raise _corrupt_lock_error(path, "invalid_ttl_seconds")
    return LockInfo(
        schema_version="1.0",
        lock_path=path,
        owner_id=owner_id,
        pid=pid,
        created_at=float(created_at),
        ttl_seconds=float(ttl_seconds),
    )


def _corrupt_lock_error(
    path: str, reason: str, *, cause: Exception | None = None
) -> AppError:
    return AppError(
        code="lock_file_corrupt",
        message="Existing lock file is malformed; inspect it before recovery",
        cause=cause,
        retryable=False,
        severity="error",
        context={"lock_path": path, "reason": reason},
    )


def _remove_created_lock_file(
    lock_path: Path, identity: tuple[int, int] | None, ctx: RunContext
) -> None:
    if identity is None:
        return
    try:
        current = lock_path.stat(follow_symlinks=False)
        if (int(current.st_dev), int(current.st_ino)) != identity:
            return
        lock_path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        logger.warning(
            log_event(
                ctx,
                role="service",
                event="lock_partial_file_cleanup_failed",
                module=logger.name,
                fields={"lock_path": str(lock_path)},
            )
        )


def get_lock(request: LockGetRequest, ctx: RunContext) -> LockGetResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="lock_get_start",
            module=logger.name,
            fields={"lock_path": request.lock_path},
        )
    )
    info = _read_lock(request.lock_path)
    response = LockGetResponse(schema_version="1.0", found=info is not None, lock=info)
    logger.info(
        log_event(
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
        )
    )
    return response


def acquire_lock(request: LockAcquireRequest, ctx: RunContext) -> LockAcquireResponse:
    logger.info(
        log_event(
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
        )
    )
    lock_path = Path(request.lock_path)
    lock_path.parent.mkdir(parents=True, exist_ok=True)
    requested_ttl = (
        float(request.ttl_seconds) if float(request.ttl_seconds) > 0 else None
    )

    existing = _read_lock(request.lock_path)
    now = time.time()
    existing_ttl = (
        float(existing.ttl_seconds) if existing and existing.ttl_seconds > 0 else None
    )
    stale_ttl = existing_ttl if existing_ttl is not None else requested_ttl
    expired = bool(existing and stale_ttl and (now - existing.created_at) > stale_ttl)
    dead_owner = bool(existing and not _owner_pid_is_alive(existing.pid))
    if existing and (expired or dead_owner):
        logger.info(
            log_event(
                ctx,
                role="service",
                event="lock_dead_owner_evicted" if dead_owner else "lock_stale_evicted",
                module=logger.name,
                fields={
                    "lock_path": request.lock_path,
                    "owner_id": existing.owner_id,
                    "pid": existing.pid,
                    "age_seconds": now - existing.created_at,
                    "eviction_reason": "dead_owner" if dead_owner else "ttl_expired",
                },
            )
        )
        try:
            lock_path.unlink(missing_ok=True)
        except OSError as exc:
            raise AppError(
                code="lock_stale_remove_failed",
                message=f"Failed to remove stale lock at {request.lock_path}",
                cause=exc,
                retryable=False,
                context={"lock_path": request.lock_path},
            ) from exc
        existing = None

    if existing:
        logger.info(
            log_event(
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
            )
        )
        return LockAcquireResponse(
            schema_version="1.0",
            acquired=False,
            lock=None,
            conflict=existing,
        )

    fd: int | None = None
    created_identity: tuple[int, int] | None = None
    try:
        fd = os.open(request.lock_path, os.O_CREAT | os.O_EXCL | os.O_WRONLY)
        created_stat = os.fstat(fd)
        created_identity = (int(created_stat.st_dev), int(created_stat.st_ino))
        payload = {
            "owner_id": request.owner_id,
            "pid": request.pid,
            "created_at": now,
        }
        if requested_ttl is not None:
            payload["ttl_seconds"] = requested_ttl
        handle = os.fdopen(fd, "w", encoding="utf-8")
        fd = None
        with handle as fh:
            json.dump(payload, fh, ensure_ascii=True)
    except FileExistsError:
        conflict = _read_lock(request.lock_path)
        logger.info(
            log_event(
                ctx,
                role="service",
                event="lock_conflict",
                module=logger.name,
                fields={
                    "lock_path": request.lock_path,
                    "existing_owner": conflict.owner_id if conflict else None,
                    "existing_pid": conflict.pid if conflict else None,
                },
            )
        )
        return LockAcquireResponse(
            schema_version="1.0",
            acquired=False,
            lock=None,
            conflict=conflict,
        )
    except (OSError, ValueError, TypeError) as exc:
        if fd is not None:
            try:
                os.close(fd)
            except OSError:
                pass
        _remove_created_lock_file(lock_path, created_identity, ctx)
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
        ttl_seconds=requested_ttl
        if requested_ttl is not None
        else DEFAULT_LOCK_TTL_SECONDS,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="lock_acquire_complete",
            module=logger.name,
            fields={
                "lock_path": request.lock_path,
                "owner_id": request.owner_id,
                "pid": request.pid,
            },
        )
    )
    return LockAcquireResponse(
        schema_version="1.0", acquired=True, lock=info, conflict=None
    )


def release_lock(request: LockReleaseRequest, ctx: RunContext) -> LockReleaseResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="lock_release_start",
            module=logger.name,
            fields={
                "lock_path": request.lock_path,
                "owner_id": request.owner_id,
                "pid": request.pid,
            },
        )
    )
    lock_path = Path(request.lock_path)
    existing = _read_lock(request.lock_path)

    if not lock_path.exists():
        logger.info(
            log_event(
                ctx,
                role="service",
                event="lock_release_missing",
                module=logger.name,
                fields={"lock_path": request.lock_path},
            )
        )
        return LockReleaseResponse(schema_version="1.0", released=False)

    if existing and existing.owner_id and existing.owner_id != request.owner_id:
        logger.info(
            log_event(
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
            )
        )
        return LockReleaseResponse(schema_version="1.0", released=False)

    try:
        lock_path.unlink(missing_ok=True)
    except OSError as exc:
        raise AppError(
            code="lock_release_failed",
            message=f"Failed to release lock at {request.lock_path}",
            cause=exc,
            retryable=False,
            context={"lock_path": request.lock_path},
        ) from exc

    logger.info(
        log_event(
            ctx,
            role="service",
            event="lock_release_complete",
            module=logger.name,
            fields={
                "lock_path": request.lock_path,
                "owner_id": request.owner_id,
                "pid": request.pid,
            },
        )
    )
    return LockReleaseResponse(schema_version="1.0", released=True)
