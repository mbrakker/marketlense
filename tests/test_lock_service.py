from __future__ import annotations

from pathlib import Path

from src.contracts.lock import (
    LockAcquireRequest,
    LockGetRequest,
    LockReleaseRequest,
)
from src.contracts.run_context import RunContext
from src.services.lock_service import acquire_lock, get_lock, release_lock


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
