from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from src.contracts.file_cache import (
    FileCacheMd5SidecarResolveResponse,
    FileCacheMd5SidecarWriteResponse,
)
from src.contracts.drive import DriveDownloadToPathResponse, DriveFile
from src.contracts.files import DeleteFileResponse, FileStatResponse
from src.contracts.ingest import IngestOutcome
from src.contracts.pdf_utils import PdfEofCheckResponse
from src.orchestrators.ingest_file_orchestrator import IngestFileDependencies, run_ingest_file


def _drive_file(*, md5_checksum: str | None) -> DriveFile:
    return DriveFile(
        schema_version="1.0",
        file_id="file-1",
        name="file-1.pdf",
        modified_time=None,
        md5_checksum=md5_checksum,
    )


def _outcome(file: DriveFile, md5: str | None) -> IngestOutcome:
    return IngestOutcome(
        schema_version="1.0",
        file_id=file.file_id,
        name=file.name or file.file_id,
        md5=md5,
        html_path="out/file-1.html",
        status="processed",
    )


def _base_dependencies(
    *,
    file_stat_fn,
    run_report_pipeline_fn,
    write_md5_sidecar_fn,
):
    return IngestFileDependencies(
        should_skip=lambda *_args, **_kwargs: False,
        cache_pdf_path=lambda settings, file: f"{settings.cache_dir}/{file.file_id}.pdf",
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
        ensure_file_name=lambda file, _settings, _ctx: file,
        write_md5_sidecar=write_md5_sidecar_fn,
        existing_report_html=lambda *_args, **_kwargs: None,
        run_step_with_retry=lambda _name, _ctx, fn, _retries: fn(),
        file_stat=file_stat_fn,
        download_pdf_to_path=lambda req, _ctx: DriveDownloadToPathResponse(
            schema_version="1.0",
            file=req.file,
            output_path=req.output_path,
            md5=None,
            size=10,
        ),
        check_pdf_eof=lambda req, _ctx: PdfEofCheckResponse(schema_version="1.0", path=req.path, has_eof=True),
        delete_file=lambda req, _ctx: DeleteFileResponse(schema_version="1.0", path=req.path, deleted=True),
        run_report_pipeline=run_report_pipeline_fn,
        state_record=lambda *_args, **_kwargs: SimpleNamespace(),
        eof_retry_limit=1,
    )


def test_missing_md5_is_computed_before_pipeline(ingest_settings, run_context):
    settings = replace(ingest_settings, vector_store_keep=True)
    file = _drive_file(md5_checksum=None)
    non_md5_calls = {"count": 0}
    compute_md5_calls = {"count": 0}
    pipeline_md5 = {"value": None}

    def _file_stat(request, _ctx):
        if request.compute_md5:
            compute_md5_calls["count"] += 1
            return FileStatResponse(
                schema_version="1.0",
                path=request.path,
                exists=True,
                size_bytes=10,
                mtime_utc=123.0,
                md5="computed-md5",
            )
        non_md5_calls["count"] += 1
        if non_md5_calls["count"] == 1:
            return FileStatResponse(
                schema_version="1.0",
                path=request.path,
                exists=False,
                size_bytes=None,
                mtime_utc=None,
                md5=None,
            )
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=True,
            size_bytes=10,
            mtime_utc=123.0,
            md5=None,
        )

    def _run_report_pipeline(current_file, _cache_path, _settings, md5, _ctx):
        pipeline_md5["value"] = md5
        return _outcome(current_file, md5)

    sidecar_writes = []
    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=_run_report_pipeline,
        write_md5_sidecar_fn=lambda request, _ctx: sidecar_writes.append(
            (
                f"{request.cache_path}.md5.json",
                request.file_id,
                request.md5,
                request.size_bytes,
                request.mtime_utc,
            )
        )
        or FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            record=None,
            written=True,
            reason="written",
        ),
    )

    result = run_ingest_file(file, 0, settings, run_context, dependencies)

    assert result.outcome.status == "processed"
    assert pipeline_md5["value"] == "computed-md5"
    assert compute_md5_calls["count"] == 1


def test_sidecar_is_written_after_computed_md5(ingest_settings, run_context):
    settings = replace(ingest_settings, vector_store_keep=True)
    file = _drive_file(md5_checksum=None)
    non_md5_calls = {"count": 0}
    sidecar_writes = []

    def _file_stat(request, _ctx):
        if request.compute_md5:
            return FileStatResponse(
                schema_version="1.0",
                path=request.path,
                exists=True,
                size_bytes=20,
                mtime_utc=456.0,
                md5="computed-sidecar-md5",
            )
        non_md5_calls["count"] += 1
        if non_md5_calls["count"] == 1:
            return FileStatResponse(
                schema_version="1.0",
                path=request.path,
                exists=False,
                size_bytes=None,
                mtime_utc=None,
                md5=None,
            )
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=True,
            size_bytes=20,
            mtime_utc=456.0,
            md5=None,
        )

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=lambda current_file, _cache_path, _settings, md5, _ctx: _outcome(current_file, md5),
        write_md5_sidecar_fn=lambda request, _ctx: sidecar_writes.append(
            (
                f"{request.cache_path}.md5.json",
                request.file_id,
                request.md5,
                request.size_bytes,
                request.mtime_utc,
            )
        )
        or FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            record=None,
            written=True,
            reason="written",
        ),
    )

    run_ingest_file(file, 0, settings, run_context, dependencies)

    assert any(write[2] == "computed-sidecar-md5" for write in sidecar_writes)


def test_existing_md5_path_unchanged_without_rehash(ingest_settings, run_context):
    settings = replace(ingest_settings, vector_store_keep=True)
    file = _drive_file(md5_checksum="drive-md5")
    compute_md5_calls = {"count": 0}
    pipeline_md5 = {"value": None}

    def _file_stat(request, _ctx):
        if request.compute_md5:
            compute_md5_calls["count"] += 1
            return FileStatResponse(
                schema_version="1.0",
                path=request.path,
                exists=True,
                size_bytes=10,
                mtime_utc=123.0,
                md5="unexpected",
            )
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=True,
            size_bytes=10,
            mtime_utc=123.0,
            md5=None,
        )

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=lambda current_file, _cache_path, _settings, md5, _ctx: (
            pipeline_md5.__setitem__("value", md5) or _outcome(current_file, md5)
        ),
        write_md5_sidecar_fn=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            record=None,
            written=False,
            reason="skipped",
        ),
    )
    dependencies = replace(
        dependencies,
        resolve_md5_sidecar=lambda request, _ctx: FileCacheMd5SidecarResolveResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            sidecar_exists=True,
            record=None,
            resolved_md5="drive-md5",
            hit=True,
            reason="matched",
        ),
    )

    result = run_ingest_file(file, 0, settings, run_context, dependencies)

    assert result.outcome.status == "processed"
    assert pipeline_md5["value"] == "drive-md5"
    assert compute_md5_calls["count"] == 0
