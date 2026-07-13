from __future__ import annotations

import logging
import os
import subprocess
import threading
from pathlib import Path

from src.contracts.run_context import RunContext
from src.contracts.ui_run_control import (
    ProcessLaunchRequest,
    ProcessLaunchResponse,
    ProcessOutputChunk,
    ProcessOutputReadRequest,
    ProcessOutputReadResponse,
    ProcessPollRequest,
    ProcessPollResponse,
    ProcessTerminateRequest,
    ProcessTerminateResponse,
)
from src.utils.clock import utc_now_iso as _utc_now
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.process_service")


_MANAGED_PROCESSES: dict[int, subprocess.Popen[bytes]] = {}
_MANAGED_PROCESSES_LOCK = threading.Lock()


def _is_windows() -> bool:
    return os.name == "nt"


def _poll_posix_process_running(pid: int) -> bool:
    waitpid = getattr(os, "waitpid", None)
    wnohang = getattr(os, "WNOHANG", 0)
    if callable(waitpid):
        try:
            waited_pid, _status = waitpid(pid, wnohang)
        except ChildProcessError:
            waited_pid = 0
        if waited_pid == pid:
            return False

    try:
        os.kill(pid, 0)
    except OSError:
        return False

    stat_path = Path("/proc") / str(pid) / "stat"
    try:
        stat_text = stat_path.read_text(encoding="utf-8", errors="replace")
    except OSError:
        return True
    stat_suffix = stat_text.rsplit(")", 1)[-1].strip()
    if stat_suffix.startswith("Z"):
        return False
    return True


def launch_process(
    request: ProcessLaunchRequest, ctx: RunContext
) -> ProcessLaunchResponse:
    command = [str(part) for part in request.command]
    cwd = str(request.cwd or "").strip()
    output_path = Path(request.output_path).expanduser().resolve()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="process_launch_start",
            module=logger.name,
            fields={
                "command": command,
                "cwd": cwd,
                "output_path": str(output_path),
            },
        )
    )
    if not command:
        raise AppError(
            code="process_command_missing",
            message="Background process command is required",
            retryable=False,
        )
    if not cwd:
        raise AppError(
            code="process_cwd_missing",
            message="Background process working directory is required",
            retryable=False,
        )
    output_path.parent.mkdir(parents=True, exist_ok=True)
    env = os.environ.copy()
    for key, value in request.env.items():
        env[str(key)] = str(value)
    creationflags = 0
    if _is_windows():
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    try:
        handle = output_path.open("ab")
    except Exception as exc:
        raise AppError(
            code="process_output_open_failed",
            message=f"Failed to open process output file: {output_path}",
            cause=exc,
            retryable=False,
            context={"output_path": str(output_path)},
        ) from exc
    try:
        if _is_windows():
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                creationflags=creationflags,
            )
        else:
            process = subprocess.Popen(
                command,
                cwd=cwd,
                stdout=handle,
                stderr=subprocess.STDOUT,
                stdin=subprocess.DEVNULL,
                env=env,
                start_new_session=True,
            )
    except Exception as exc:
        handle.close()
        raise AppError(
            code="process_launch_failed",
            message="Failed to launch background process",
            cause=exc,
            retryable=False,
            context={"command": command, "cwd": cwd},
        ) from exc
    finally:
        handle.close()
    response = ProcessLaunchResponse(
        schema_version="1.0",
        pid=int(process.pid),
        command=command,
        cwd=cwd,
        output_path=str(output_path),
        started_at_utc=_utc_now(),
    )
    with _MANAGED_PROCESSES_LOCK:
        _MANAGED_PROCESSES[response.pid] = process
    logger.info(
        log_event(
            ctx,
            role="service",
            event="process_launch_complete",
            module=logger.name,
            fields={
                "pid": response.pid,
                "command": response.command,
                "cwd": response.cwd,
                "output_path": response.output_path,
                "started_at_utc": response.started_at_utc,
            },
        )
    )
    return response


def poll_process(request: ProcessPollRequest, ctx: RunContext) -> ProcessPollResponse:
    pid = int(request.pid)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="process_poll_start",
            module=logger.name,
            fields={"pid": pid},
        )
    )
    running = False
    try:
        with _MANAGED_PROCESSES_LOCK:
            process = _MANAGED_PROCESSES.get(pid)
        if process is not None:
            running = process.poll() is None
            if not running:
                with _MANAGED_PROCESSES_LOCK:
                    _MANAGED_PROCESSES.pop(pid, None)
        elif _is_windows():
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
            )
            output = str(result.stdout or "").strip()
            running = bool(output) and "no tasks are running" not in output.lower()
        else:
            running = _poll_posix_process_running(pid)
    except OSError:
        running = False
    response = ProcessPollResponse(schema_version="1.0", pid=pid, running=running)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="process_poll_complete",
            module=logger.name,
            fields={"pid": pid, "running": running},
        )
    )
    return response


def terminate_process(
    request: ProcessTerminateRequest, ctx: RunContext
) -> ProcessTerminateResponse:
    pid = int(request.pid)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="process_terminate_start",
            module=logger.name,
            fields={"pid": pid},
        )
    )
    terminated = True
    try:
        with _MANAGED_PROCESSES_LOCK:
            process = _MANAGED_PROCESSES.get(pid)
        if process is not None:
            process.terminate()
            try:
                process.wait(timeout=5)
            except subprocess.TimeoutExpired:
                process.kill()
                process.wait(timeout=5)
            finally:
                with _MANAGED_PROCESSES_LOCK:
                    _MANAGED_PROCESSES.pop(pid, None)
        elif _is_windows():
            result = subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
            if result.returncode != 0:
                details = " ".join(
                    part.strip()
                    for part in (str(result.stdout or ""), str(result.stderr or ""))
                    if part and str(part).strip()
                ).strip()
                lowered = details.lower()
                if not any(
                    marker in lowered
                    for marker in (
                        "not found",
                        "no running instance",
                        "no tasks are running",
                    )
                ):
                    raise AppError(
                        code="process_terminate_failed",
                        message=f"Failed to terminate process {pid}",
                        retryable=False,
                        context={"pid": pid, "details": details},
                    )
        else:
            getpgid = getattr(os, "getpgid", None)
            killpg = getattr(os, "killpg", None)
            if not callable(getpgid) or not callable(killpg):
                raise AppError(
                    code="process_terminate_unsupported_platform",
                    message="Process-group termination is not supported on this platform",
                    retryable=False,
                    context={"pid": pid},
                )
            killpg(getpgid(pid), 15)
    except ProcessLookupError:
        logger.info(
            log_event(
                ctx,
                role="service",
                event="process_terminate_already_absent",
                module=logger.name,
                fields={"pid": pid},
            )
        )
    except OSError as exc:
        raise AppError(
            code="process_terminate_failed",
            message=f"Failed to terminate process {pid}",
            cause=exc,
            retryable=False,
            context={"pid": pid},
        ) from exc
    response = ProcessTerminateResponse(
        schema_version="1.0",
        pid=pid,
        terminated=terminated,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="process_terminate_complete",
            module=logger.name,
            fields={"pid": pid, "terminated": terminated},
        )
    )
    return response


def read_process_output(
    request: ProcessOutputReadRequest, ctx: RunContext
) -> ProcessOutputReadResponse:
    path = Path(request.path).expanduser().resolve()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="process_output_read_start",
            module=logger.name,
            fields={"path": str(path), "max_bytes": request.max_bytes},
        )
    )
    if not path.exists():
        chunk = ProcessOutputChunk(
            schema_version="1.0",
            path=str(path),
            text="",
            truncated=False,
            size_bytes=0,
        )
        return ProcessOutputReadResponse(schema_version="1.0", chunk=chunk)
    try:
        size_bytes = int(path.stat().st_size)
        with path.open("rb") as handle:
            if size_bytes > request.max_bytes:
                handle.seek(max(0, size_bytes - int(request.max_bytes)))
                raw = handle.read()
                truncated = True
            else:
                raw = handle.read()
                truncated = False
    except Exception as exc:
        raise AppError(
            code="process_output_read_failed",
            message=f"Failed to read process output: {path}",
            cause=exc,
            retryable=False,
            context={"path": str(path)},
        ) from exc
    chunk = ProcessOutputChunk(
        schema_version="1.0",
        path=str(path),
        text=raw.decode("utf-8", errors="replace"),
        truncated=truncated,
        size_bytes=size_bytes,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="process_output_read_complete",
            module=logger.name,
            fields={
                "path": chunk.path,
                "truncated": chunk.truncated,
                "size_bytes": chunk.size_bytes,
            },
        )
    )
    return ProcessOutputReadResponse(schema_version="1.0", chunk=chunk)
