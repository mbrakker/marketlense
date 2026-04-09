from __future__ import annotations

import logging
import os
import subprocess
from datetime import datetime, timezone
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
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.process_service")


def _utc_now() -> str:
    return datetime.now(timezone.utc).isoformat()


def _is_windows() -> bool:
    return os.name == "nt"


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
    popen_kwargs: dict[str, object] = {}
    if _is_windows():
        creationflags = getattr(subprocess, "CREATE_NEW_PROCESS_GROUP", 0)
    else:
        popen_kwargs["start_new_session"] = True
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
        process = subprocess.Popen(
            command,
            cwd=cwd,
            stdout=handle,
            stderr=subprocess.STDOUT,
            stdin=subprocess.DEVNULL,
            env=env,
            creationflags=creationflags,
            **popen_kwargs,
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
        if _is_windows():
            result = subprocess.run(
                ["tasklist", "/FI", f"PID eq {pid}", "/FO", "CSV", "/NH"],
                capture_output=True,
                text=True,
                check=False,
            )
            output = str(result.stdout or "").strip()
            running = bool(output) and "no tasks are running" not in output.lower()
        else:
            os.kill(pid, 0)
            running = True
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
    try:
        if _is_windows():
            subprocess.run(
                ["taskkill", "/PID", str(pid), "/T", "/F"],
                capture_output=True,
                text=True,
                check=False,
            )
        else:
            os.killpg(os.getpgid(pid), 15)
    except ProcessLookupError:
        pass
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
        terminated=True,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="process_terminate_complete",
            module=logger.name,
            fields={"pid": pid, "terminated": True},
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
