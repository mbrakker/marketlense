from __future__ import annotations

from src.orchestrators import ingest_orchestrator
from src.orchestrators._ingest_orchestrator import db_preflight, lock_lifecycle


def test_ingest_orchestrator_keeps_run_ingest_facade_and_private_owners() -> None:
    assert callable(ingest_orchestrator.run_ingest)
    assert callable(lock_lifecycle.acquire_ingest_lock)
    assert callable(lock_lifecycle.finalize_ingest_run)
    assert callable(db_preflight.verify_ingest_db_access)


def test_ingest_facade_delegates_lock_and_db_lifecycle() -> None:
    source = ingest_orchestrator.__loader__.get_source(ingest_orchestrator.__name__)

    assert "acquire_ingest_lock(settings, lock_ctx)" in source
    assert "verify_ingest_db_access(settings, root_ctx)" in source
    assert "finalize_ingest_run(" in source
    assert "def _acquire_ingest_lock" not in source
    assert "def _verify_ingest_db_access" not in source
