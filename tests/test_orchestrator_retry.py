from __future__ import annotations

import hashlib
import logging
from dataclasses import replace
from pathlib import Path
from types import SimpleNamespace

from src.contracts.file_cache import (
    FileCacheMd5SidecarResolveResponse,
    FileCacheMd5SidecarWriteResponse,
)
from src.contracts.drive import DriveDownloadToPathResponse, DriveFile
from src.contracts.pdf_utils import PdfEofCheckResponse
from src.orchestrators import ingest_orchestrator as orch
from src.orchestrators import report_pipeline_orchestrator as report_pipeline_orch
from src.orchestrators import retry_orchestrator as retry_orch
from src.orchestrators.ingest_file_orchestrator import (
    IngestFileDependencies,
    run_ingest_file,
)
from src.utils.errors import AppError


def _pdf_bytes() -> bytes:
    return b"%PDF-1.4\n1 0 obj <</Type/Catalog>> endobj\n%%EOF\n"


def test_retry_on_retryable_app_error(
    ingest_settings,
    app_paths,
    external_boundary_mocks_only,
) -> None:
    settings = replace(
        ingest_settings,
        batch_limit=1,
        ingest_worker_limit=1,
        output_dir=app_paths["output_dir"],
        cache_dir=app_paths["cache_dir"],
    )
    drive_file = DriveFile(
        schema_version="1.0",
        file_id="file-1",
        name="retry.pdf",
        modified_time=None,
        md5_checksum="md5",
    )
    retry_error = AppError(
        code="openai_request_failed",
        message="retry",
        retryable=True,
    )
    attempt_count = {"value": 0}
    sleep_calls: list[int] = []

    external_boundary_mocks_only.setattr(
        retry_orch.random,
        "uniform",
        lambda _a, _b: 0.0,
    )
    external_boundary_mocks_only.setattr(
        report_pipeline_orch.time,
        "sleep",
        lambda seconds: sleep_calls.append(int(seconds)),
    )

    def _download(req, ctx):
        payload = _pdf_bytes()
        out_path = Path(req.output_path)
        out_path.parent.mkdir(parents=True, exist_ok=True)
        out_path.write_bytes(payload)
        return DriveDownloadToPathResponse(
            schema_version="1.0",
            file=req.file,
            output_path=req.output_path,
            md5="md5",
            size=len(payload),
        )

    def _file_stat(req, ctx):
        path = Path(req.path)
        if not path.exists():
            return SimpleNamespace(
                exists=False,
                size_bytes=None,
                mtime_utc=None,
                md5=None,
            )
        payload = path.read_bytes()
        md5 = (
            hashlib.md5(payload).hexdigest()
            if getattr(req, "compute_md5", False)
            else None
        )
        return SimpleNamespace(
            exists=True,
            size_bytes=len(payload),
            mtime_utc=path.stat().st_mtime,
            md5=md5,
        )

    def _run_step_with_retry(step_name, ctx, operation, retries):
        return retry_orch.run_step_with_default_policy(
            step_name=step_name,
            operation=operation,
            ctx=ctx,
            logger=logging.getLogger("market_lense.test_orchestrator_retry"),
            module_name="market_lense.test_orchestrator_retry",
            retries=retries,
            sleep_fn=report_pipeline_orch.time.sleep,
        )

    def _generate_report(file, cache_path, current_settings, md5, ctx):
        attempt_count["value"] += 1
        raise retry_error

    def _run_report_pipeline(file, cache_path, current_settings, md5, ctx):
        return report_pipeline_orch.run_report_pipeline(
            file,
            cache_path,
            current_settings,
            md5,
            ctx,
            retries=2,
            generate_report_fn=_generate_report,
        )

    def _process_file(file, index, current_settings, root_ctx):
        dependencies = IngestFileDependencies(
            should_skip=lambda *_args, **_kwargs: False,
            cache_pdf_path=lambda settings_obj, drive: str(
                Path(settings_obj.cache_dir) / f"{drive.file_id}.pdf"
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
            ensure_file_name=lambda current_file, *_args, **_kwargs: current_file,
            write_md5_sidecar=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
                schema_version="1.0",
                cache_path=request.cache_path,
                sidecar_path=f"{request.cache_path}.md5.json",
                record=None,
                written=False,
                reason="skipped",
            ),
            existing_report_html=lambda *_args, **_kwargs: None,
            run_step_with_retry=_run_step_with_retry,
            file_stat=_file_stat,
            download_pdf_to_path=_download,
            check_pdf_eof=lambda req, ctx: PdfEofCheckResponse(
                schema_version="1.0",
                path=req.path,
                has_eof=True,
            ),
            delete_file=lambda req, ctx: None,
            run_report_pipeline=_run_report_pipeline,
            state_record=lambda req, ctx: None,
            eof_retry_limit=1,
        )
        return run_ingest_file(
            file=file,
            index=index,
            settings=current_settings,
            root_ctx=root_ctx,
            dependencies=dependencies,
            logger_name="market_lense.test_orchestrator_retry",
        )

    outcomes = orch.run_ingest(
        settings,
        limit=1,
        dependencies=orch.IngestBatchDependencies(
            list_pdfs=lambda req, ctx: [drive_file],
            batch_should_skip=lambda *_args, **_kwargs: {},
            process_file=_process_file,
            thread_pool_executor_factory=orch.ThreadPoolExecutor,
            flush_uncategorized_tags=lambda req, ctx: None,
        ),
    )

    assert len(outcomes) == 1
    assert outcomes[0].file_id == "file-1"
    assert outcomes[0].name == "retry.pdf"
    assert outcomes[0].status == "error"
    assert outcomes[0].error == "retry"
    assert attempt_count["value"] == 3
    assert sleep_calls == [1, 2]
