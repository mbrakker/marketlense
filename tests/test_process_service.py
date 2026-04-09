from __future__ import annotations

import logging
import sys
import time
from pathlib import Path

import pytest

from src.contracts.ui_run_control import (
    ProcessLaunchRequest,
    ProcessOutputReadRequest,
    ProcessPollRequest,
    ProcessTerminateRequest,
)
from src.services.process_service import (
    launch_process,
    poll_process,
    read_process_output,
    terminate_process,
)
from src.utils.errors import AppError
from src.utils.logging import new_run_context


def _ctx():
    return new_run_context(task_id="test_process_service")


def test_process_service_launch_poll_and_output_roundtrip(
    tmp_path: Path,
    caplog,
    assert_logs_have_required_fields,
) -> None:
    output_path = tmp_path / "process.log"
    caplog.set_level(logging.INFO)

    response = launch_process(
        ProcessLaunchRequest(
            schema_version="1.0",
            command=[
                sys.executable,
                "-c",
                "import sys; print('stdout-line', flush=True); print('stderr-line', file=sys.stderr, flush=True)",
            ],
            cwd=str(tmp_path),
            output_path=str(output_path),
        ),
        _ctx(),
    )

    deadline = time.time() + 10
    running = True
    while time.time() < deadline:
        poll = poll_process(
            ProcessPollRequest(schema_version="1.0", pid=response.pid),
            _ctx(),
        )
        running = poll.running
        if not running:
            break
        time.sleep(0.1)

    chunk = read_process_output(
        ProcessOutputReadRequest(
            schema_version="1.0",
            path=str(output_path),
            max_bytes=4096,
        ),
        _ctx(),
    ).chunk

    assert running is False
    assert "stdout-line" in chunk.text
    assert "stderr-line" in chunk.text
    assert chunk.size_bytes > 0
    assert_logs_have_required_fields(caplog.records)


def test_process_service_terminate_running_process(tmp_path: Path) -> None:
    output_path = tmp_path / "sleep.log"
    response = launch_process(
        ProcessLaunchRequest(
            schema_version="1.0",
            command=[
                sys.executable,
                "-c",
                "import time; print('started', flush=True); time.sleep(30)",
            ],
            cwd=str(tmp_path),
            output_path=str(output_path),
        ),
        _ctx(),
    )

    terminate_process(
        ProcessTerminateRequest(schema_version="1.0", pid=response.pid),
        _ctx(),
    )

    deadline = time.time() + 10
    while time.time() < deadline:
        poll = poll_process(
            ProcessPollRequest(schema_version="1.0", pid=response.pid),
            _ctx(),
        )
        if not poll.running:
            break
        time.sleep(0.1)

    assert poll.running is False


def test_process_service_missing_cwd_returns_typed_error(assert_app_error) -> None:
    with pytest.raises(AppError) as exc_info:
        launch_process(
            ProcessLaunchRequest(
                schema_version="1.0",
                command=[sys.executable, "-c", "print('x')"],
                cwd="",
                output_path="out.log",
            ),
            _ctx(),
        )

    assert_app_error(exc_info.value, code="process_cwd_missing", retryable=False)
