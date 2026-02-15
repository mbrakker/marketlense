from __future__ import annotations

from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Lock, get_ident

from src.contracts.drive import DriveDownloadToPathResponse, DriveFile
from src.contracts.ingest import IngestOutcome
from src.contracts.state import (
    StateBatchCheckResponse,
    StateProcessedListRequest,
)
from src.orchestrators import ingest_orchestrator as orch
from src.services.state_service import list_processed


class _DummyExecutor:
    def __init__(self, max_workers: int, captured: dict[str, int]) -> None:
        self.max_workers = max_workers
        captured["max_workers"] = max_workers

    def __enter__(self):
        return self

    def __exit__(self, exc_type, exc, tb):
        return False

    def submit(self, fn, *args, **kwargs):
        future = Future()
        try:
            future.set_result(fn(*args, **kwargs))
        except Exception as exc:
            future.set_exception(exc)
        return future


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj <</Type/Catalog>> endobj\n%%EOF\n"


def test_parallel_executor_orders_results(ingest_settings, monkeypatch) -> None:
    settings = replace(ingest_settings, batch_limit=2, ingest_worker_limit=2)
    files = [
        DriveFile(schema_version="1.0", file_id="file_a", name="a.pdf", modified_time=None, md5_checksum="md5a"),
        DriveFile(schema_version="1.0", file_id="file_b", name="b.pdf", modified_time=None, md5_checksum="md5b"),
    ]
    outcomes = [
        IngestOutcome(
            schema_version="1.0",
            file_id="file_a",
            name="a.pdf",
            md5="md5a",
            html_path="out/a.html",
            status="processed",
        ),
        IngestOutcome(
            schema_version="1.0",
            file_id="file_b",
            name="b.pdf",
            md5="md5b",
            html_path="out/b.html",
            status="processed",
        ),
    ]
    captured: dict[str, int] = {}

    def _fake_process(file, index, current_settings, root_ctx):
        return orch._FileProcessResult(index=index, outcome=outcomes[index], processed=1, had_error=False)

    monkeypatch.setattr(orch, "list_pdfs", lambda req, ctx: files)
    monkeypatch.setattr(orch, "ThreadPoolExecutor", lambda max_workers: _DummyExecutor(max_workers, captured))
    monkeypatch.setattr(orch, "_process_file", _fake_process)

    results = orch.run_ingest(settings, limit=2)

    assert captured.get("max_workers") == 2
    assert [row.file_id for row in results] == ["file_a", "file_b"]


def test_parallel_executor_uses_real_concurrency(ingest_settings, run_context, monkeypatch) -> None:
    settings = replace(ingest_settings, batch_limit=2, ingest_worker_limit=2)
    files = [
        DriveFile(schema_version="1.0", file_id="file_a", name="a.pdf", modified_time=None, md5_checksum="md5a"),
        DriveFile(schema_version="1.0", file_id="file_b", name="b.pdf", modified_time=None, md5_checksum="md5b"),
    ]
    barrier = Barrier(2)
    thread_ids: set[int] = set()
    thread_lock = Lock()

    def _download(req, ctx):
        payload = _pdf_bytes()
        out_path = Path(req.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        return DriveDownloadToPathResponse(
            schema_version="1.0",
            file=req.file,
            output_path=req.output_path,
            md5=req.file.md5_checksum,
            size=len(payload),
        )

    def _generate_report(file, cache_path, current_settings, md5, ctx):
        with thread_lock:
            thread_ids.add(get_ident())
        barrier.wait(timeout=3.0)
        html_path = Path(current_settings.output_dir) / f"{file.file_id}.html"
        html_path.write_text("<html>ok</html>", encoding="utf-8")
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name or file.file_id,
            md5=md5,
            html_path=str(html_path),
            status="processed",
        )

    monkeypatch.setattr(orch, "list_pdfs", lambda req, ctx: files)
    monkeypatch.setattr(orch, "download_pdf_to_path", _download)
    monkeypatch.setattr(orch, "generate_report", _generate_report)

    results = orch.run_ingest(settings, limit=2, ctx=run_context)

    assert [row.status for row in results] == ["processed", "processed"]
    assert {row.file_id for row in results} == {"file_a", "file_b"}
    assert len(thread_ids) == 2
    state_rows = list_processed(
        StateProcessedListRequest(schema_version="1.0", state_db=settings.state_db, limit=10),
        run_context,
    ).rows
    assert {row.file_id for row in state_rows} == {"file_a", "file_b"}


def test_ingest_uses_batch_state_prefilter(ingest_settings, monkeypatch) -> None:
    settings = replace(ingest_settings, batch_limit=2, ingest_worker_limit=1)
    files = [
        DriveFile(schema_version="1.0", file_id="file_a", name="a.pdf", modified_time=None, md5_checksum="md5a"),
        DriveFile(schema_version="1.0", file_id="file_b", name="b.pdf", modified_time=None, md5_checksum="md5b"),
        DriveFile(schema_version="1.0", file_id="file_c", name="c.pdf", modified_time=None, md5_checksum="md5c"),
    ]
    batch_calls = {"count": 0}

    def _batch_check(request, ctx):
        batch_calls["count"] += 1
        processed = [item for item in request.items if item.file_id == "file_a"]
        return StateBatchCheckResponse(
            schema_version="1.0",
            state_db=request.state_db,
            processed_items=processed,
        )

    def _unexpected_single_check(_request, _ctx):
        raise AssertionError("expected drive-list filtering to use batch state checks")

    def _fake_process(file, index, current_settings, root_ctx):
        return orch._FileProcessResult(
            index=index,
            outcome=IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=file.name or file.file_id,
                md5=file.md5_checksum,
                html_path=f"out/{file.file_id}.html",
                status="processed",
            ),
            processed=1,
            had_error=False,
        )

    monkeypatch.setattr(orch, "list_pdfs", lambda req, ctx: files)
    monkeypatch.setattr(orch, "state_already_processed_batch", _batch_check)
    monkeypatch.setattr(orch, "state_already_processed", _unexpected_single_check)
    monkeypatch.setattr(orch, "_process_file", _fake_process)

    results = orch.run_ingest(settings, limit=2)

    assert batch_calls["count"] == 1
    assert [row.file_id for row in results] == ["file_b", "file_c"]


def test_ingest_does_not_repeat_drive_md5_single_state_check(ingest_settings, monkeypatch) -> None:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    file = DriveFile(schema_version="1.0", file_id="file_a", name="a.pdf", modified_time=None, md5_checksum="md5a")
    single_calls = {"count": 0}

    def _batch_check(request, ctx):
        return StateBatchCheckResponse(
            schema_version="1.0",
            state_db=request.state_db,
            processed_items=[],
        )

    def _single_check(_request, _ctx):
        single_calls["count"] += 1
        return False

    def _download(req, ctx):
        payload = _pdf_bytes()
        out_path = Path(req.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        return DriveDownloadToPathResponse(
            schema_version="1.0",
            file=req.file,
            output_path=req.output_path,
            md5=req.file.md5_checksum,
            size=len(payload),
        )

    def _generate_report(file, cache_path, current_settings, md5, ctx):
        html_path = Path(current_settings.output_dir) / f"{file.file_id}.html"
        html_path.write_text("<html>ok</html>", encoding="utf-8")
        return IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.name or file.file_id,
            md5=md5,
            html_path=str(html_path),
            status="processed",
        )

    monkeypatch.setattr(orch, "list_pdfs", lambda req, ctx: [file])
    monkeypatch.setattr(orch, "state_already_processed_batch", _batch_check)
    monkeypatch.setattr(orch, "state_already_processed", _single_check)
    monkeypatch.setattr(orch, "download_pdf_to_path", _download)
    monkeypatch.setattr(orch, "generate_report", _generate_report)

    results = orch.run_ingest(settings, limit=1)

    assert [row.status for row in results] == ["processed"]
    assert single_calls["count"] == 0
