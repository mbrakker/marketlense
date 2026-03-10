from __future__ import annotations

from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Lock, get_ident
from types import SimpleNamespace

from src.contracts.drive import DriveDownloadToPathResponse, DriveFile
from src.contracts.ingest import IngestOutcome
from src.contracts.state import StateBatchCheckResponse, StateProcessedListRequest
from src.orchestrators import ingest_orchestrator as orch
from src.orchestrators.ingest_file_orchestrator import (
    IngestFileDependencies,
    run_ingest_file,
)
from src.services.file_service import file_stat
from src.services.state_service import list_processed, record as state_record


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


def _batch_dependencies(**overrides):
    return replace(orch.IngestBatchDependencies.default(), **overrides)


def _make_real_process_file(
    *,
    download_pdf_to_path,
    run_report_pipeline,
    should_skip=None,
):
    def _process_file(file, index, settings, root_ctx):
        file_dependencies = IngestFileDependencies(
            should_skip=should_skip or (lambda *_args: False),
            cache_pdf_path=lambda current_settings, current_file: str(
                Path(current_settings.cache_dir) / f"{current_file.file_id}.pdf"
            ),
            md5_sidecar_path=lambda cache_path: f"{cache_path}.md5.json",
            load_md5_sidecar=lambda *_args: None,
            sidecar_md5_for_stat=lambda *_args: None,
            ensure_file_name=lambda current_file, _settings, _ctx: current_file,
            write_md5_sidecar=lambda *_args: None,
            existing_report_html=lambda *_args: None,
            run_step_with_retry=lambda _step, _ctx, operation, _retries: operation(),
            file_stat=file_stat,
            download_pdf_to_path=download_pdf_to_path,
            check_pdf_eof=lambda _request, _ctx: SimpleNamespace(has_eof=True),
            delete_file=lambda _request, _ctx: None,
            run_report_pipeline=run_report_pipeline,
            state_record=state_record,
            eof_retry_limit=0,
        )
        return run_ingest_file(
            file=file,
            index=index,
            settings=settings,
            root_ctx=root_ctx,
            dependencies=file_dependencies,
            logger_name=orch.logger.name,
        )

    return _process_file


def test_parallel_executor_orders_results(ingest_settings) -> None:
    settings = replace(ingest_settings, batch_limit=2, ingest_worker_limit=2)
    files = [
        DriveFile(
            schema_version="1.0",
            file_id="file_a",
            name="a.pdf",
            modified_time=None,
            md5_checksum="md5a",
        ),
        DriveFile(
            schema_version="1.0",
            file_id="file_b",
            name="b.pdf",
            modified_time=None,
            md5_checksum="md5b",
        ),
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
    current_settings = settings

    def _fake_process_file(file, index, settings, root_ctx):
        assert settings == current_settings
        assert root_ctx.run_id
        return orch._FileProcessResult(
            index=index,
            outcome=outcomes[index],
            processed=1,
            had_error=False,
        )

    deps = _batch_dependencies(
        list_pdfs=lambda req, ctx: files,
        process_file=_fake_process_file,
        thread_pool_executor_factory=lambda max_workers: _DummyExecutor(
            max_workers, captured
        ),
    )

    results = orch.run_ingest(settings, limit=2, dependencies=deps)

    assert captured.get("max_workers") == 2
    assert [row.file_id for row in results] == ["file_a", "file_b"]


def test_parallel_executor_uses_real_concurrency(ingest_settings, run_context) -> None:
    settings = replace(ingest_settings, batch_limit=2, ingest_worker_limit=2)
    files = [
        DriveFile(
            schema_version="1.0",
            file_id="file_a",
            name="a.pdf",
            modified_time=None,
            md5_checksum="md5a",
        ),
        DriveFile(
            schema_version="1.0",
            file_id="file_b",
            name="b.pdf",
            modified_time=None,
            md5_checksum="md5b",
        ),
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

    deps = _batch_dependencies(
        list_pdfs=lambda req, ctx: files,
        process_file=_make_real_process_file(
            download_pdf_to_path=_download,
            run_report_pipeline=_generate_report,
        ),
    )

    results = orch.run_ingest(settings, limit=2, ctx=run_context, dependencies=deps)

    assert [row.status for row in results] == ["processed", "processed"]
    assert {row.file_id for row in results} == {"file_a", "file_b"}
    assert len(thread_ids) == 2
    state_rows = list_processed(
        StateProcessedListRequest(
            schema_version="1.0", state_db=settings.state_db, limit=10
        ),
        run_context,
    ).rows
    assert {row.file_id for row in state_rows} == {"file_a", "file_b"}


def test_ingest_uses_batch_state_prefilter(ingest_settings) -> None:
    settings = replace(ingest_settings, batch_limit=2, ingest_worker_limit=1)
    files = [
        DriveFile(
            schema_version="1.0",
            file_id="file_a",
            name="a.pdf",
            modified_time=None,
            md5_checksum="md5a",
        ),
        DriveFile(
            schema_version="1.0",
            file_id="file_b",
            name="b.pdf",
            modified_time=None,
            md5_checksum="md5b",
        ),
        DriveFile(
            schema_version="1.0",
            file_id="file_c",
            name="c.pdf",
            modified_time=None,
            md5_checksum="md5c",
        ),
    ]
    batch_calls = {"count": 0}
    current_settings = settings

    def _batch_check(files_to_check, state_db, ctx):
        batch_calls["count"] += 1
        assert state_db == settings.state_db
        return {
            (file.file_id, file.md5_checksum): file.file_id == "file_a"
            for file in files_to_check
            if file.md5_checksum
        }

    def _fake_process_file(file, index, settings, root_ctx):
        assert settings == current_settings
        assert root_ctx.run_id
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

    deps = _batch_dependencies(
        list_pdfs=lambda req, ctx: files,
        batch_should_skip=_batch_check,
        process_file=_fake_process_file,
    )

    results = orch.run_ingest(settings, limit=2, dependencies=deps)

    assert batch_calls["count"] == 1
    assert [row.file_id for row in results] == ["file_b", "file_c"]


def test_ingest_does_not_repeat_drive_md5_single_state_check(ingest_settings) -> None:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    file = DriveFile(
        schema_version="1.0",
        file_id="file_a",
        name="a.pdf",
        modified_time=None,
        md5_checksum="md5a",
    )
    single_calls = {"count": 0}

    def _batch_check(files_to_check, state_db, ctx):
        return {
            (current_file.file_id, current_file.md5_checksum): False
            for current_file in files_to_check
            if current_file.md5_checksum
        }

    def _single_check(_file, _md5, _state_db, _ctx):
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

    deps = _batch_dependencies(
        list_pdfs=lambda req, ctx: [file],
        batch_should_skip=_batch_check,
        process_file=_make_real_process_file(
            download_pdf_to_path=_download,
            run_report_pipeline=_generate_report,
            should_skip=_single_check,
        ),
    )

    results = orch.run_ingest(settings, limit=1, dependencies=deps)

    assert [row.status for row in results] == ["processed"]
    assert single_calls["count"] == 0
