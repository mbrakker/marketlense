from __future__ import annotations

import json
import multiprocessing
import os
import subprocess
import sys
from pathlib import Path
from queue import Empty

import pytest

from src.contracts.lock import LockAcquireRequest, LockGetRequest
from src.contracts.run_context import RunContext
from src.services.lock_service import acquire_lock, get_lock


def _ctx() -> RunContext:
    return RunContext(schema_version="1.0", run_id="r", task_id="t", span_id="s")


def _acquire_after_barrier(lock_path, owner_id, barrier, results, release_winner):
    try:
        barrier.wait(timeout=10)
        response = acquire_lock(
            LockAcquireRequest(
                schema_version="1.0",
                lock_path=str(lock_path),
                owner_id=owner_id,
                pid=os.getpid(),
                ttl_seconds=3600,
            ),
            _ctx(),
        )
        results.put(
            (
                owner_id,
                response.acquired,
                response.lock.generation if response.lock else None,
            )
        )
        if response.acquired:
            release_winner.wait(timeout=15)
    except BaseException as exc:
        results.put((owner_id, "error", type(exc).__name__))


def _guard_handle(lock_path):
    """Acquire the documented OS guard to simulate a writer at its file boundary."""
    guard_path = Path(f"{lock_path}.coord")
    guard_path.parent.mkdir(parents=True, exist_ok=True)
    handle = guard_path.open("a+b")
    if os.name == "nt":
        import msvcrt

        handle.seek(0, os.SEEK_END)
        if handle.tell() == 0:
            handle.write(b"\0")
            handle.flush()
        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_LOCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_EX)
    return handle


def _unlock_guard(handle):
    if os.name == "nt":
        import msvcrt

        handle.seek(0)
        msvcrt.locking(handle.fileno(), msvcrt.LK_UNLCK, 1)
    else:
        import fcntl

        fcntl.flock(handle.fileno(), fcntl.LOCK_UN)
    handle.close()


def _write_partial_lock_while_guarded(lock_path, owner_pid, ready, finish, crash):
    handle = _guard_handle(lock_path)
    Path(lock_path).write_text('{"owner_id":"half-written"', encoding="utf-8")
    ready.set()
    if crash:
        os._exit(0)
    if not finish.wait(timeout=10):
        os._exit(3)
    Path(lock_path).write_text(
        json.dumps(
            {
                "owner_id": "mid-write-owner",
                "pid": owner_pid,
                "created_at": 1.0,
                "ttl_seconds": 3600.0,
            }
        ),
        encoding="utf-8",
    )
    _unlock_guard(handle)


def _read_lock_after_start(lock_path, started, results):
    started.set()
    try:
        response = get_lock(
            LockGetRequest(schema_version="1.0", lock_path=str(lock_path)), _ctx()
        )
        results.put(
            (
                response.found,
                response.lock.owner_id if response.lock else None,
                response.lock.pid if response.lock else None,
            )
        )
    except BaseException as exc:
        results.put(("error", type(exc).__name__))


def test_two_simultaneous_acquisitions_have_one_live_owner(tmp_path: Path) -> None:
    mp = multiprocessing.get_context("spawn")
    lock_path = tmp_path / "shared.lock"
    barrier = mp.Barrier(3)
    results = mp.Queue()
    release_winner = mp.Event()
    processes = [
        mp.Process(
            target=_acquire_after_barrier,
            args=(lock_path, f"owner-{index}", barrier, results, release_winner),
        )
        for index in range(2)
    ]
    for process in processes:
        process.start()
    try:
        barrier.wait(timeout=10)
        outcomes = [results.get(timeout=10), results.get(timeout=10)]
        assert all(outcome[1] != "error" for outcome in outcomes)
        assert sum(outcome[1] is True for outcome in outcomes) == 1
        current = get_lock(
            LockGetRequest(schema_version="1.0", lock_path=str(lock_path)), _ctx()
        )
        assert current.found is True
        assert current.lock is not None
        assert current.lock.owner_id == next(
            outcome[0] for outcome in outcomes if outcome[1] is True
        )
    finally:
        release_winner.set()
        for process in processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)


def test_reader_waits_for_a_guarded_mid_creation_write(tmp_path: Path) -> None:
    mp = multiprocessing.get_context("spawn")
    lock_path = tmp_path / "mid-write.lock"
    ready = mp.Event()
    finish = mp.Event()
    started = mp.Event()
    results = mp.Queue()
    writer = mp.Process(
        target=_write_partial_lock_while_guarded,
        args=(lock_path, os.getpid(), ready, finish, False),
    )
    writer.start()
    reader = None
    try:
        assert ready.wait(timeout=10)
        reader = mp.Process(
            target=_read_lock_after_start, args=(lock_path, started, results)
        )
        reader.start()
        assert started.wait(timeout=10)
        with pytest.raises(Empty):
            results.get(timeout=0.2)
        finish.set()
        result = results.get(timeout=10)
        assert result == (True, "mid-write-owner", os.getpid())
    finally:
        finish.set()
        writer.join(timeout=10)
        if writer.is_alive():
            writer.terminate()
            writer.join(timeout=5)
        if reader is not None:
            reader.join(timeout=10)
            if reader.is_alive():
                reader.terminate()
                reader.join(timeout=5)


def test_process_crash_after_partial_lock_creation_is_recovered(
    tmp_path: Path,
) -> None:
    mp = multiprocessing.get_context("spawn")
    lock_path = tmp_path / "crashed.lock"
    ready = mp.Event()
    finish = mp.Event()
    writer = mp.Process(
        target=_write_partial_lock_while_guarded,
        args=(lock_path, os.getpid(), ready, finish, True),
    )
    writer.start()
    assert ready.wait(timeout=10)
    writer.join(timeout=10)
    assert writer.exitcode == 0
    assert lock_path.read_text(encoding="utf-8") == '{"owner_id":"half-written"'

    recovered = acquire_lock(
        LockAcquireRequest(
            schema_version="1.0",
            lock_path=str(lock_path),
            owner_id="recovered-owner",
            pid=os.getpid(),
            ttl_seconds=3600,
        ),
        _ctx(),
    )

    assert recovered.acquired is True
    assert recovered.lock is not None
    assert recovered.lock.owner_id == "recovered-owner"
    persisted = json.loads(lock_path.read_text(encoding="utf-8"))
    assert persisted["owner_id"] == "recovered-owner"
    assert persisted["generation"] == recovered.lock.generation


def test_concurrent_dead_owner_eviction_has_one_successor(tmp_path: Path) -> None:
    mp = multiprocessing.get_context("spawn")
    lock_path = tmp_path / "expired.lock"
    dead_owner = subprocess.Popen([sys.executable, "-c", "pass"])
    dead_owner.wait(timeout=10)
    lock_path.write_text(
        json.dumps(
            {
                "owner_id": "dead-owner",
                "pid": dead_owner.pid,
                "created_at": 1.0,
                "ttl_seconds": 3600,
                "generation": "old-generation",
            }
        ),
        encoding="utf-8",
    )
    barrier = mp.Barrier(3)
    results = mp.Queue()
    release_winner = mp.Event()
    processes = [
        mp.Process(
            target=_acquire_after_barrier,
            args=(lock_path, f"successor-{index}", barrier, results, release_winner),
        )
        for index in range(2)
    ]
    for process in processes:
        process.start()
    try:
        barrier.wait(timeout=10)
        outcomes = [results.get(timeout=10), results.get(timeout=10)]
        assert all(outcome[1] != "error" for outcome in outcomes)
        assert sum(outcome[1] is True for outcome in outcomes) == 1
        persisted = json.loads(lock_path.read_text(encoding="utf-8"))
        winner = next(outcome for outcome in outcomes if outcome[1] is True)
        assert persisted["owner_id"] == winner[0]
        assert persisted["generation"] == winner[2]
    finally:
        release_winner.set()
        for process in processes:
            process.join(timeout=10)
            if process.is_alive():
                process.terminate()
                process.join(timeout=5)
