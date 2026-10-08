from __future__ import annotations

import ctypes
import errno
import json
import logging
import math
import os
import sys
import tempfile
import time
import uuid
from contextlib import contextmanager, suppress
from pathlib import Path
from typing import Iterator, Optional

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


@contextmanager
def _coordination_guard(lock_path: Path) -> Iterator[None]:
    """Serialize lock-file operations with a persistent OS-locked sidecar."""
    guard_path = Path(f"{lock_path}.coord")
    handle = None
    overlapped = None
    try:
        guard_path.parent.mkdir(parents=True, exist_ok=True)
        handle = guard_path.open("a+b")
        if sys.platform == "win32":
            import msvcrt
            from ctypes import wintypes

            class _Overlapped(ctypes.Structure):
                _fields_ = [
                    ("Internal", ctypes.c_void_p),
                    ("InternalHigh", ctypes.c_void_p),
                    ("Offset", wintypes.DWORD),
                    ("OffsetHigh", wintypes.DWORD),
                    ("hEvent", wintypes.HANDLE),
                ]

            overlapped = _Overlapped()
            kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
            lock_file_ex = kernel32.LockFileEx
            lock_file_ex.argtypes = [
                wintypes.HANDLE,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                wintypes.DWORD,
                ctypes.POINTER(_Overlapped),
            ]
            lock_file_ex.restype = wintypes.BOOL
            handle_value = msvcrt.get_osfhandle(handle.fileno())
            if not lock_file_ex(
                handle_value,
                0x00000002,  # LOCKFILE_EXCLUSIVE_LOCK; wait in the kernel.
                0,
                1,
                0,
                ctypes.byref(overlapped),
            ):
                raise ctypes.WinError(ctypes.get_last_error())
        else:
            import fcntl

            fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
        try:
            yield
        finally:
            if sys.platform == "win32":
                import msvcrt
                from ctypes import wintypes

                kernel32 = ctypes.WinDLL("kernel32", use_last_error=True)
                unlock_file_ex = kernel32.UnlockFileEx
                unlock_file_ex.argtypes = [
                    wintypes.HANDLE,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    wintypes.DWORD,
                    ctypes.POINTER(type(overlapped)),
                ]
                unlock_file_ex.restype = wintypes.BOOL
                if not unlock_file_ex(
                    msvcrt.get_osfhandle(handle.fileno()),
                    0,
                    1,
                    0,
                    ctypes.byref(overlapped),
                ):
                    raise ctypes.WinError(ctypes.get_last_error())
            else:
                import fcntl

                fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    except AppError:
        raise
    except OSError as exc:
        raise AppError(
            code="lock_coordination_failed",
            message="Failed to coordinate filesystem lock operations",
            cause=exc,
            retryable=True,
            context={"lock_path": str(lock_path)},
        ) from exc
    finally:
        if handle is not None:
            handle.close()


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
        return exc.errno != errno.ESRCH
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
    generation = data.get("generation")
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
    if generation is not None and (
        not isinstance(generation, str) or not generation.strip()
    ):
        raise _corrupt_lock_error(path, "invalid_generation")
    return LockInfo(
        schema_version="1.0",
        lock_path=path,
        owner_id=owner_id,
        pid=pid,
        created_at=float(created_at),
        ttl_seconds=float(ttl_seconds),
        generation=generation,
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
    file_path: Path, identity: tuple[int, int] | None, ctx: RunContext
) -> None:
    if identity is None:
        return
    try:
        current = file_path.stat(follow_symlinks=False)
        if (int(current.st_dev), int(current.st_ino)) != identity:
            return
        file_path.unlink()
    except FileNotFoundError:
        return
    except OSError:
        logger.warning(
            log_event(
                ctx,
                role="service",
                event="lock_partial_file_cleanup_failed",
                module=logger.name,
                fields={"lock_path": str(file_path)},
            )
        )


def _write_lock_atomically(
    lock_path: Path,
    payload: dict[str, object],
    ctx: RunContext,
) -> None:
    fd: int | None = None
    temp_path: Path | None = None
    temp_identity: tuple[int, int] | None = None
    try:
        fd, raw_temp_path = tempfile.mkstemp(
            prefix=f".{lock_path.name}.",
            suffix=".tmp",
            dir=lock_path.parent,
        )
        temp_path = Path(raw_temp_path)
        temp_stat = os.fstat(fd)
        temp_identity = (int(temp_stat.st_dev), int(temp_stat.st_ino))
        with os.fdopen(fd, "w", encoding="utf-8") as handle:
            fd = None
            json.dump(payload, handle, ensure_ascii=True)
            handle.flush()
            os.fsync(handle.fileno())
        os.replace(temp_path, lock_path)
    except (OSError, ValueError, TypeError) as exc:
        if fd is not None:
            with suppress(OSError):
                os.close(fd)
        if temp_path is not None:
            _remove_created_lock_file(temp_path, temp_identity, ctx)
        raise AppError(
            code="lock_acquire_failed",
            message=f"Failed to acquire lock at {lock_path}",
            cause=exc,
            retryable=False,
            context={"lock_path": str(lock_path)},
        ) from exc


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
    with _coordination_guard(Path(request.lock_path)):
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
    requested_ttl = (
        float(request.ttl_seconds) if float(request.ttl_seconds) > 0 else None
    )
    with _coordination_guard(lock_path):
        try:
            existing = _read_lock(request.lock_path)
        except AppError as exc:
            if exc.code != "lock_file_corrupt":
                raise
            try:
                lock_path.unlink(missing_ok=True)
            except OSError:
                raise exc from None
            reason = (
                str(exc.context.get("reason", "unknown"))
                if isinstance(exc.context, dict)
                else "unknown"
            )
            logger.warning(
                log_event(
                    ctx,
                    role="service",
                    event="lock_malformed_record_recovered",
                    module=logger.name,
                    fields={"lock_path": request.lock_path, "reason": reason},
                )
            )
            existing = None

        now = time.time()
        existing_ttl = (
            float(existing.ttl_seconds)
            if existing and existing.ttl_seconds > 0
            else None
        )
        stale_ttl = existing_ttl if existing_ttl is not None else requested_ttl
        expired = bool(
            existing and stale_ttl and (now - existing.created_at) > stale_ttl
        )
        dead_owner = bool(existing and not _owner_pid_is_alive(existing.pid))
        if existing and (expired or dead_owner):
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event=(
                        "lock_dead_owner_evicted"
                        if dead_owner
                        else "lock_stale_evicted"
                    ),
                    module=logger.name,
                    fields={
                        "lock_path": request.lock_path,
                        "owner_id": existing.owner_id,
                        "pid": existing.pid,
                        "age_seconds": now - existing.created_at,
                        "eviction_reason": (
                            "dead_owner" if dead_owner else "ttl_expired"
                        ),
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

        generation = uuid.uuid4().hex
        payload: dict[str, object] = {
            "owner_id": request.owner_id,
            "pid": request.pid,
            "created_at": now,
            "generation": generation,
        }
        if requested_ttl is not None:
            payload["ttl_seconds"] = requested_ttl
        _write_lock_atomically(lock_path, payload, ctx)

        info = LockInfo(
            schema_version="1.0",
            lock_path=request.lock_path,
            owner_id=request.owner_id,
            pid=request.pid,
            created_at=now,
            ttl_seconds=requested_ttl
            if requested_ttl is not None
            else DEFAULT_LOCK_TTL_SECONDS,
            generation=generation,
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
    with _coordination_guard(lock_path):
        existing = _read_lock(request.lock_path)
        if existing is None:
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

        same_owner = (
            existing.owner_id == request.owner_id and existing.pid == request.pid
        )
        same_generation = (
            request.generation is None
            if existing.generation is None
            else request.generation == existing.generation
        )
        if not same_owner or not same_generation:
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
            lock_path.unlink()
        except FileNotFoundError:
            return LockReleaseResponse(schema_version="1.0", released=False)
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
