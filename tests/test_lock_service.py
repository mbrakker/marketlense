from __future__ import annotations

from pathlib import Path

import pytest

from src.contracts.lock import (
    LockAcquireRequest,
    LockGetRequest,
    LockReleaseRequest,
)
from src.contracts.run_context import RunContext
from src.services.lock_service import acquire_lock, get_lock, release_lock
from src.utils.errors import AppError


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def test_get_lock_reflects_lock_lifecycle(tmp_path: Path) -> None:
    lock_path = tmp_path / "ingest.lock"
    before = get_lock(LockGetRequest(schema_version="1.0", lock_path=str(lock_path)), _ctx())
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
    current = get_lock(LockGetRequest(schema_version="1.0", lock_path=str(lock_path)), _ctx())
    assert current.found is True
    assert current.lock is not None
    assert current.lock.owner_id == "owner-1"

    released = release_lock(
        LockReleaseRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="owner-1",
            pid=1001,
        ),
        _ctx(),
    )
    assert released.released is True
    after = get_lock(LockGetRequest(schema_version="1.0", lock_path=str(lock_path)), _ctx())
    assert after.found is False


def test_release_lock_wraps_os_error_as_typed_app_error(
    monkeypatch, tmp_path: Path, assert_app_error
) -> None:
    lock_path = tmp_path / "ingest.lock"
    lock_path.write_text(
        '{"owner_id":"owner-1","pid":1001,"created_at":1.0}',
        encoding="utf-8",
    )

    def _raise_unlink(self, *, missing_ok=False):
        raise PermissionError("denied")

    monkeypatch.setattr(Path, "unlink", _raise_unlink)

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
