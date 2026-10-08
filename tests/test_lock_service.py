from __future__ import annotations

import logging
import os
import subprocess
import sys
from pathlib import Path

import pytest

from src.contracts.lock import (
    LockAcquireRequest,
    LockGetRequest,
    LockReleaseRequest,
)
from src.contracts.run_context import RunContext
from src.services import lock_service
from src.services.lock_service import acquire_lock, get_lock, release_lock
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_running_local_pid_is_alive() -> None:
    assert lock_service._owner_pid_is_alive(os.getpid()) is True


def test_get_lock_reflects_lock_lifecycle(tmp_path: Path) -> None:
    lock_path = tmp_path / "ingest.lock"
    before = get_lock(
        LockGetRequest(schema_version="1.0", lock_path=str(lock_path)), _ctx()
    )
    assert before.found is False
    assert before.lock is None

    acquired = acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="owner-1",
            pid=1001,
            ttl_seconds=3600,
        ),
        _ctx(),
    )
    assert acquired.acquired is True
    assert acquired.lock is not None
    current = get_lock(
        LockGetRequest(schema_version="1.0", lock_path=str(lock_path)), _ctx()
    )
    assert current.found is True
    assert current.lock is not None
    assert current.lock.owner_id == "owner-1"

    released = release_lock(
        LockReleaseRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="owner-1",
            pid=1001,
            generation=acquired.lock.generation,
        ),
        _ctx(),
    )
    assert released.released is True
    after = get_lock(
        LockGetRequest(schema_version="1.0", lock_path=str(lock_path)), _ctx()
    )
    assert after.found is False


def test_release_lock_wraps_os_error_as_typed_app_error(
    external_boundary_mocks_only, tmp_path: Path, assert_app_error
) -> None:
    lock_path = tmp_path / "ingest.lock"
    lock_path.write_text(
        '{"owner_id":"owner-1","pid":1001,"created_at":1.0}',
        encoding="utf-8",
    )

    def _raise_unlink(self, *, missing_ok=False):
        raise PermissionError("denied")

    external_boundary_mocks_only.setattr(Path, "unlink", _raise_unlink)

    with pytest.raises(AppError) as exc_info:
        release_lock(
            LockReleaseRequest(
                schema_version="1.0",
                lock_path=str(lock_path),
                owner_id="owner-1",
                pid=1001,
            ),
            _ctx(),
        )

    assert_app_error(exc_info.value, code="lock_release_failed", retryable=False)


def test_acquire_lock_does_not_steal_live_lock_with_tiny_request_ttl(
    tmp_path: Path,
    external_boundary_mocks_only,
) -> None:
    lock_path = tmp_path / "ingest.lock"
    current_time = {"value": 1000.0}
    external_boundary_mocks_only.setattr(
        lock_service.time,
        "time",
        lambda: current_time["value"],
    )

    first = acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="owner-a",
            pid=os.getpid(),
            ttl_seconds=3600.0,
        ),
        _ctx(),
    )
    current_time["value"] += 0.02
    second = acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="owner-b",
            pid=1002,
            ttl_seconds=0.001,
        ),
        _ctx(),
    )

    assert first.acquired is True
    assert second.acquired is False
    assert second.conflict is not None
    assert second.conflict.owner_id == "owner-a"


def test_acquire_lock_reclaims_a_dead_local_owner_before_ttl_expiry(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "ingest.lock"
    owner = subprocess.Popen([sys.executable, "-c", "pass"])
    owner.wait(timeout=5)
    lock_path.write_text(
        '{"owner_id":"interrupted-owner","pid":'
        + str(owner.pid)
        + ',"created_at":9999999999.0,"ttl_seconds":7200.0}',
        encoding="utf-8",
    )

    acquired = acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="replacement-owner",
            pid=os.getpid(),
            ttl_seconds=7200.0,
        ),
        _ctx(),
    )

    assert acquired.acquired is True
    assert acquired.lock is not None
    assert acquired.lock.owner_id == "replacement-owner"


def test_stale_generation_release_cannot_remove_replacement_owner(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "generation.lock"
    dead_owner = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_owner.wait(timeout=5)
    first = acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="first-owner",
            pid=dead_owner.pid,
            ttl_seconds=3600,
        ),
        _ctx(),
    )
    assert first.acquired is True
    assert first.lock is not None
    assert first.lock.generation

    replacement = acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="replacement-owner",
            pid=os.getpid(),
            ttl_seconds=3600,
        ),
        _ctx(),
    )
    assert replacement.acquired is True
    assert replacement.lock is not None
    assert replacement.lock.generation != first.lock.generation

    stale_release = release_lock(
        LockReleaseRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id=first.lock.owner_id,
            pid=first.lock.pid,
            generation=first.lock.generation,
        ),
        _ctx(),
    )

    assert stale_release.released is False
    current = get_lock(
        LockGetRequest(schema_version="1.0", lock_path=str(lock_path)), _ctx()
    )
    assert current.lock is not None
    assert current.lock.owner_id == "replacement-owner"
    assert current.lock.generation == replacement.lock.generation


def test_legacy_release_is_exact_and_cannot_release_new_generation(
    tmp_path: Path,
) -> None:
    lock_path = tmp_path / "legacy.lock"
    lock_path.write_text(
        '{"owner_id":"legacy-owner","pid":' + str(os.getpid()) + ',"created_at":1.0}',
        encoding="utf-8",
    )
    legacy_release = release_lock(
        LockReleaseRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="legacy-owner",
            pid=os.getpid(),
        ),
        _ctx(),
    )
    assert legacy_release.released is True

    current = acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="current-owner",
            pid=os.getpid(),
            ttl_seconds=3600,
        ),
        _ctx(),
    )
    assert current.acquired is True
    assert current.lock is not None

    tokenless_release = release_lock(
        LockReleaseRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="current-owner",
            pid=os.getpid(),
        ),
        _ctx(),
    )
    assert tokenless_release.released is False

    wrong_generation_release = release_lock(
        LockReleaseRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="current-owner",
            pid=os.getpid(),
            generation="not-current",
        ),
        _ctx(),
    )
    assert wrong_generation_release.released is False
    assert lock_path.exists()


@pytest.mark.parametrize(
    "payload",
    [
        "{",
        "[]",
        "null",
        "{}",
        '{"owner_id":"private-lock-marker","pid":1,"created_at":NaN}',
    ],
)
def test_get_lock_diagnoses_and_acquire_recovers_corrupt_existing_lock(
    payload: str, tmp_path: Path, caplog
) -> None:
    lock_path = tmp_path / "ingest.lock"
    lock_path.write_text(payload, encoding="utf-8")
    caplog.set_level(logging.INFO)

    with pytest.raises(AppError) as read_error:
        get_lock(LockGetRequest(schema_version="1.0", lock_path=str(lock_path)), _ctx())

    assert read_error.value.code == "lock_file_corrupt"
    acquired = acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="replacement-owner",
            pid=os.getpid(),
            ttl_seconds=3600,
        ),
        _ctx(),
    )

    assert acquired.acquired is True
    assert acquired.lock is not None
    assert acquired.lock.owner_id == "replacement-owner"
    assert "private-lock-marker" not in caplog.text


def test_failed_initial_lock_write_removes_only_the_created_file(
    tmp_path: Path, external_boundary_mocks_only
) -> None:
    lock_path = tmp_path / "ingest.lock"
    unrelated_file = tmp_path / ".ingest.lock.unrelated.tmp"
    unrelated_file.write_text("preserve", encoding="utf-8")

    def fail_replace(source, destination):
        raise OSError("simulated atomic lock write failure")

    external_boundary_mocks_only.setattr(lock_service.os, "replace", fail_replace)

    with pytest.raises(AppError) as exc_info:
        acquire_lock(
            LockAcquireRequest(
                schema_version="1.0",
                lock_path=str(lock_path),
                owner_id="owner-1",
                pid=os.getpid(),
                ttl_seconds=3600,
            ),
            _ctx(),
        )

    assert exc_info.value.code == "lock_acquire_failed"
    assert lock_path.exists() is False
    assert unrelated_file.read_text(encoding="utf-8") == "preserve"
    assert list(tmp_path.glob(".ingest.lock.*.tmp")) == [unrelated_file]
