from __future__ import annotations

import json
from concurrent.futures import Future
from dataclasses import replace
from pathlib import Path
from threading import Barrier, Lock, get_ident
from types import SimpleNamespace

import pytest

from src.contracts.drive import DriveDownloadToPathResponse, DriveFile
from src.contracts.file_cache import (
    FileCacheMd5SidecarResolveResponse,
    FileCacheMd5SidecarWriteResponse,
)
from src.contracts.ingest import IngestOutcome
from src.contracts.remediation import RemediationListRequest
from src.contracts.state import (
    StateGetResponse,
    StateIngestCursorSetRequest,
    StateProcessedListRequest,
    StateRecordRequest,
)
from src.orchestrators import ingest_orchestrator as orch
from src.orchestrators.ingest_file_orchestrator import (
    IngestFileDependencies,
    run_ingest_file,
)
from src.services.file_service import delete_file, file_stat
from src.services.pdf_service import check_pdf_eof
from src.services.state_service import list_processed, list_remediation_records
from src.services.state_service import record as state_record
from src.utils.errors import AppError


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
    existing_report_html=None,
    bypass_existing_report_html: bool = False,
):
    def _process_file(file, index, settings, root_ctx, force_report_cards):
        file_dependencies = IngestFileDependencies(
            should_skip=should_skip or (lambda *_args: False),
            cache_pdf_path=lambda current_settings, current_file: str(
                Path(current_settings.cache_dir) / f"{current_file.file_id}.pdf"
            ),
            resolve_md5_sidecar=lambda request, _ctx: (
                FileCacheMd5SidecarResolveResponse(
                    schema_version="1.0",
                    cache_path=request.cache_path,
                    sidecar_path=f"{request.cache_path}.md5.json",
                    sidecar_exists=False,
                    record=None,
                    resolved_md5=None,
                    hit=False,
                    reason="missing",
                )
            ),
            ensure_file_name=lambda current_file, _settings, _ctx: current_file,
            write_md5_sidecar=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
                schema_version="1.0",
                cache_path=request.cache_path,
                sidecar_path=f"{request.cache_path}.md5.json",
                record=None,
                written=False,
                reason="skipped",
            ),
            existing_report_html=existing_report_html or (lambda *_args: None),
            run_step_with_retry=lambda _step, _ctx, operation, _retries: operation(),
            file_stat=file_stat,
            download_pdf_to_path=download_pdf_to_path,
            check_pdf_eof=lambda _request, _ctx: SimpleNamespace(has_eof=True),
            delete_file=lambda _request, _ctx: None,
            run_report_pipeline=run_report_pipeline,
            state_record=state_record,
            eof_retry_limit=0,
            bypass_existing_report_html=(
                bypass_existing_report_html or force_report_cards
            ),
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


def _valid_report_card_manifest_payload() -> dict[str, object]:
    return {
        "schema_version": "1.0",
        "title": "Global Economic Conditions Quarterly Update",
        "title_scale": "long",
        "publisher": "McKinsey & Company",
        "published_date": "2026-06-09",
        "geography_label": "Global",
        "geography_scope": "global",
        "covered_period": "Q2 2026",
        "tldr_compact": "Complete compact TLDR.",
        "tldr_standard": "Complete standard TLDR with grounded context.",
        "key_insights": ["First insight.", "Second insight."],
        "fingerprint": {
            "schema_version": "1.0",
            "geometry_family": "ascending_trajectory",
            "evidence_shape": "trend",
            "direction": "rising",
            "geography_scope": "global",
            "evidence_density": "balanced",
            "domain_layer": "grid",
            "seed": 184221,
            "selection_reason": "A rising trend dominates the report.",
        },
        "covers": {
            "schema_version": "1.0",
            "small": {
                "schema_version": "1.0",
                "size": "small",
                "output_path": "assets/report-card-small.png",
                "width": 1600,
                "height": 900,
            },
            "medium": {
                "schema_version": "1.0",
                "size": "medium",
                "output_path": "assets/report-card-medium.png",
                "width": 1200,
                "height": 1500,
            },
            "large": {
                "schema_version": "1.0",
                "size": "large",
                "output_path": "assets/report-card-large.png",
                "width": 1200,
                "height": 1600,
            },
        },
    }


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

    def _fake_process_file(file, index, settings, root_ctx, force_report_cards):
        del force_report_cards
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


def test_drive_cache_prefetch_downloads_and_hashes_before_report_workers(
    ingest_settings,
    run_context,
    external_boundary_mocks_only,
) -> None:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    file = DriveFile(
        schema_version="1.0",
        file_id="prefetch-file",
        name="Prefetch.pdf",
        modified_time=None,
        md5_checksum=None,
    )
    download_calls: list[str] = []
    download_requests = []

    def _download(req, ctx):
        del ctx
        payload = _pdf_bytes()
        out_path = Path(req.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        download_calls.append(req.file.file_id)
        download_requests.append(req)
        return DriveDownloadToPathResponse(
            schema_version="1.0",
            file=req.file,
            output_path=req.output_path,
            md5=None,
            size=len(payload),
        )

    external_boundary_mocks_only.setattr(orch, "download_pdf_to_path", _download)

    prefetched_files = orch._prefetch_drive_cache_stage(
        [file],
        settings=settings,
        deps=orch.IngestBatchDependencies.default(),
        root_ctx=run_context,
    )

    cache_path = Path(settings.cache_dir) / "prefetch-file.pdf"
    sidecar_path = Path(f"{cache_path}.md5.json")
    assert download_calls == ["prefetch-file"]
    assert download_requests[0].run_budget is not None
    assert download_requests[0].run_budget.run_id == run_context.run_id
    assert download_requests[0].run_budget.usage_db_path == settings.usage_db_path
    assert cache_path.exists()
    assert sidecar_path.exists()
    assert prefetched_files[0].md5_checksum


def test_ingest_file_refreshes_cached_pdf_without_eof_before_generation(
    ingest_settings,
    run_context,
) -> None:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    file = DriveFile(
        schema_version="1.0",
        file_id="corrupt-cache-file",
        name="Corrupt cache.pdf",
        modified_time=None,
        md5_checksum=None,
    )
    cache_path = Path(settings.cache_dir) / f"{file.file_id}.pdf"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    cache_path.write_bytes(b"%PDF-1.4\ntruncated body without trailer\n")
    download_calls: list[str] = []

    def _download(req, ctx):
        del ctx
        payload = _pdf_bytes()
        Path(req.output_path).write_bytes(payload)
        download_calls.append(req.file.file_id)
        return DriveDownloadToPathResponse(
            schema_version="1.0",
            file=req.file,
            output_path=req.output_path,
            md5=None,
            size=len(payload),
        )

    def _generate_report(current_file, current_cache_path, current_settings, md5, ctx):
        del current_settings, ctx
        assert current_file.file_id == file.file_id
        assert current_cache_path == str(cache_path)
        assert download_calls == [file.file_id]
        assert Path(current_cache_path).read_bytes().endswith(b"%%EOF\n")
        assert md5
        return IngestOutcome(
            schema_version="1.0",
            file_id=current_file.file_id,
            name=current_file.name or current_file.file_id,
            md5=md5,
            html_path=str(Path(settings.output_dir) / "corrupt-cache-file.html"),
            status="processed",
        )

    dependencies = IngestFileDependencies(
        should_skip=lambda *_args: False,
        cache_pdf_path=lambda _settings, _file: str(cache_path),
        resolve_md5_sidecar=lambda request, _ctx: FileCacheMd5SidecarResolveResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            sidecar_exists=False,
            record=None,
            resolved_md5=None,
            hit=False,
            reason="missing",
        ),
        ensure_file_name=lambda current_file, _settings, _ctx: current_file,
        write_md5_sidecar=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            record=None,
            written=bool(request.md5),
            reason="written" if request.md5 else "incomplete_metadata",
        ),
        existing_report_html=lambda *_args: None,
        run_step_with_retry=lambda _step, _ctx, operation, _retries: operation(),
        file_stat=file_stat,
        download_pdf_to_path=_download,
        check_pdf_eof=check_pdf_eof,
        delete_file=delete_file,
        run_report_pipeline=_generate_report,
        state_record=state_record,
        eof_retry_limit=0,
    )

    result = run_ingest_file(
        file=file,
        index=0,
        settings=settings,
        root_ctx=run_context,
        dependencies=dependencies,
        logger_name=orch.logger.name,
    )

    assert result.outcome.status == "processed"
    assert result.processed == 1
    assert result.had_error is False


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

    def _fake_process_file(file, index, settings, root_ctx, force_report_cards):
        del force_report_cards
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


def test_ingest_limit_uses_cursor_unless_rescan_requested(ingest_settings) -> None:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    cursor = "2026-06-15T12:00:00Z"
    orch.set_ingest_cursor(
        StateIngestCursorSetRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            last_successful_ingest_utc=cursor,
        ),
        orch.new_run_context(),
    )

    modified_after = orch._resolve_modified_after(
        settings,
        limit=1,
        force_report_cards=False,
        rescan=False,
        root_ctx=orch.new_run_context(),
    )
    rescan_modified_after = orch._resolve_modified_after(
        settings,
        limit=1,
        force_report_cards=False,
        rescan=True,
        root_ctx=orch.new_run_context(),
    )

    assert modified_after == cursor
    assert rescan_modified_after is None


def test_ingest_retries_doc_map_empty_state_when_text_validation_passed(
    ingest_settings,
) -> None:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    retry_file = DriveFile(
        schema_version="1.0",
        file_id="file_retry",
        name="retry.pdf",
        modified_time=None,
        md5_checksum="md5-retry",
    )
    next_file = DriveFile(
        schema_version="1.0",
        file_id="file_next",
        name="next.pdf",
        modified_time=None,
        md5_checksum="md5-next",
    )
    state_record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id=retry_file.file_id,
            md5="md5-retry",
            last_error="doc_map_empty:no_content",
            text_validation_status="pass",
            doc_map_summary={"has_content": False, "not_found_reason": "no_content"},
        ),
        orch.new_run_context(),
    )

    def _fake_process_file(file, index, settings, root_ctx, force_report_cards):
        del force_report_cards
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
        list_pdfs=lambda req, ctx: [retry_file, next_file],
        process_file=_fake_process_file,
    )

    results = orch.run_ingest(settings, limit=1, dependencies=deps)

    assert [row.file_id for row in results] == ["file_retry"]


def test_ingest_retries_progress_state_without_final_text_validation(
    ingest_settings,
) -> None:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    progress_file = DriveFile(
        schema_version="1.0",
        file_id="file_progress",
        name="progress.pdf",
        modified_time=None,
        md5_checksum="md5-progress",
    )
    next_file = DriveFile(
        schema_version="1.0",
        file_id="file_next",
        name="next.pdf",
        modified_time=None,
        md5_checksum="md5-next",
    )
    state_record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id=progress_file.file_id,
            md5="md5-progress",
            vector_store_status="completed",
        ),
        orch.new_run_context(),
    )

    def _fake_process_file(file, index, settings, root_ctx, force_report_cards):
        del force_report_cards
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
        list_pdfs=lambda req, ctx: [progress_file, next_file],
        process_file=_fake_process_file,
    )

    results = orch.run_ingest(settings, limit=1, dependencies=deps)

    assert [row.file_id for row in results] == ["file_progress"]


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


def test_force_report_cards_resume_from_analysis_only_for_existing_html() -> None:
    assert orch._report_pipeline_resume_options(
        force_report_cards=True,
        has_existing_report_html=True,
        auto_resume_from_latest_safe=True,
    ) == ("analysis_complete", False)
    assert orch._report_pipeline_resume_options(
        force_report_cards=False,
        has_existing_report_html=True,
        auto_resume_from_latest_safe=True,
    ) == (None, True)
    assert orch._report_pipeline_resume_options(
        force_report_cards=True,
        has_existing_report_html=False,
        auto_resume_from_latest_safe=True,
    ) == (None, True)


def test_force_report_cards_bypasses_existing_html_cache(ingest_settings) -> None:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    file = DriveFile(
        schema_version="1.0",
        file_id="file-card-cache",
        name="Card Cache.pdf",
        modified_time=None,
        md5_checksum="card-cache-md5",
    )
    generated: list[str] = []

    def _download(req, ctx):
        del ctx
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

    def _generate_report(current_file, cache_path, current_settings, md5, ctx):
        del cache_path, ctx
        generated.append(current_file.file_id)
        return IngestOutcome(
            schema_version="1.1",
            file_id=current_file.file_id,
            name=current_file.name or current_file.file_id,
            md5=md5,
            html_path=str(Path(current_settings.output_dir) / "card-cache.html"),
            report_card_manifest_path=str(
                Path(current_settings.output_dir)
                / "card-cache"
                / "report-card-manifest.json"
            ),
            status="processed",
        )

    deps = _batch_dependencies(
        list_pdfs=lambda req, ctx: [file],
        batch_should_skip=lambda files, state_db, ctx: {
            (file.file_id, file.md5_checksum or ""): False
        },
        process_file=_make_real_process_file(
            download_pdf_to_path=_download,
            run_report_pipeline=_generate_report,
            existing_report_html=lambda *_args: "out/card-cache.html",
            bypass_existing_report_html=True,
        ),
        vector_store_retention_cleanup=lambda settings, ctx: None,
    )

    results = orch.run_ingest(settings, limit=1, dependencies=deps)

    assert [row.status for row in results] == ["processed"]
    assert generated == [file.file_id]


def _run_report_card_backfill_case(
    ingest_settings,
    *,
    force_report_cards: bool,
    manifest_exists: bool,
    manifest_content: str,
) -> list[tuple[str, bool]]:
    settings = replace(ingest_settings, batch_limit=1, ingest_worker_limit=1)
    file = DriveFile(
        schema_version="1.0",
        file_id="file-card",
        name="Card Report.pdf",
        modified_time="2026-06-10T00:00:00Z",
        md5_checksum="card-md5",
    )
    processed: list[tuple[str, bool]] = []

    def _process(
        current_file,
        index,
        current_settings,
        root_ctx,
        force_current_report_cards,
    ):
        del current_settings, root_ctx
        processed.append((current_file.file_id, force_current_report_cards))
        return orch._FileProcessResult(
            index=index,
            outcome=IngestOutcome(
                schema_version="1.1",
                file_id=current_file.file_id,
                name=current_file.name or current_file.file_id,
                md5=current_file.md5_checksum,
                html_path="out/card-report.html",
                status="processed",
            ),
            processed=1,
            had_error=False,
        )

    deps = _batch_dependencies(
        list_pdfs=lambda req, ctx: [file],
        batch_should_skip=lambda files, state_db, ctx: {
            (file.file_id, file.md5_checksum or ""): True
        },
        process_file=_process,
        file_exists=lambda req, ctx: SimpleNamespace(exists=manifest_exists),
        read_text=lambda req, ctx: SimpleNamespace(content=manifest_content),
        vector_store_retention_cleanup=lambda settings, ctx: None,
    )

    orch.run_ingest(
        settings,
        limit=1,
        force_report_cards=force_report_cards,
        dependencies=deps,
    )
    return processed


def test_report_cards_normal_mode_keeps_processed_report_skipped(
    ingest_settings,
) -> None:
    processed = _run_report_card_backfill_case(
        ingest_settings,
        force_report_cards=False,
        manifest_exists=False,
        manifest_content="",
    )

    assert processed == []


def test_report_cards_force_mode_reprocesses_missing_manifest(
    ingest_settings,
) -> None:
    processed = _run_report_card_backfill_case(
        ingest_settings,
        force_report_cards=True,
        manifest_exists=False,
        manifest_content="",
    )

    assert processed == [("file-card", True)]


def test_report_cards_force_mode_reprocesses_invalid_manifest(
    ingest_settings,
) -> None:
    processed = _run_report_card_backfill_case(
        ingest_settings,
        force_report_cards=True,
        manifest_exists=True,
        manifest_content='{"schema_version":"1.0"}',
    )

    assert processed == [("file-card", True)]


def test_ingest_batch_failure_creates_operator_held_remediation(
    ingest_settings,
    run_context,
) -> None:
    dependencies = _batch_dependencies(
        list_pdfs=lambda _request, _ctx: (_ for _ in ()).throw(
            AppError(
                code="drive_listing_unavailable",
                message="drive listing unavailable",
                retryable=False,
                severity="error",
            )
        ),
        vector_store_retention_cleanup=lambda _settings, _ctx: None,
    )

    with pytest.raises(AppError, match="drive listing unavailable"):
        orch.run_ingest(
            ingest_settings,
            limit=1,
            ctx=run_context,
            dependencies=dependencies,
        )

    records = list_remediation_records(
        RemediationListRequest(
            schema_version="1.0",
            state_db=ingest_settings.state_db,
            workflow="ingest",
        ),
        run_context,
    ).records
    assert len(records) == 1
    assert records[0].error_code == "drive_listing_unavailable"
    assert records[0].status == "operator_action_required"


def test_report_cards_force_mode_skips_valid_manifest(ingest_settings) -> None:
    processed = _run_report_card_backfill_case(
        ingest_settings,
        force_report_cards=True,
        manifest_exists=True,
        manifest_content=json.dumps(_valid_report_card_manifest_payload()),
    )

    assert processed == []


def test_checkpoint_lineage_failure_is_selected_for_repair() -> None:
    record = StateGetResponse(
        schema_version="1.0",
        file_id="failed-report",
        md5="failed-md5",
        processed_at=1,
        last_error=(
            "report_pipeline_checkpoint_lineage_not_reusable: "
            "Checkpoint artifact lineage cannot be reused"
        ),
    )

    assert orch._processed_record_should_skip(record, orch.new_run_context()) is False


def test_report_card_backfill_uses_canonical_report_metadata_path(
    ingest_settings,
) -> None:
    file = DriveFile(
        schema_version="1.0",
        file_id="file-card",
        name="file-card",
        modified_time=None,
        md5_checksum="card-md5",
    )
    checked_paths: list[str] = []

    def _file_exists(request, ctx):
        del ctx
        checked_paths.append(request.path)
        return SimpleNamespace(exists=True)

    deps = _batch_dependencies(
        get_report_metadata=lambda request, ctx: SimpleNamespace(
            html_path="out/canonical-report.html"
        ),
        file_exists=_file_exists,
        read_text=lambda request, ctx: SimpleNamespace(
            content=json.dumps(_valid_report_card_manifest_payload())
        ),
    )

    should_skip = orch._report_card_backfill_should_skip(
        file,
        settings=ingest_settings,
        deps=deps,
        root_ctx=orch.new_run_context(),
    )

    assert should_skip is True
    assert checked_paths == [
        str(Path("out/canonical-report") / "report-card-manifest.json")
    ]
