from __future__ import annotations

from dataclasses import replace
from types import SimpleNamespace

from src.contracts.drive import DriveDownloadToPathResponse, DriveFile
from src.contracts.file_cache import (
    FileCacheMd5SidecarResolveResponse,
    FileCacheMd5SidecarWriteResponse,
)
from src.contracts.files import DeleteFileResponse, FileStatResponse
from src.contracts.ingest import IngestOutcome
from src.contracts.pdf_utils import PdfEofCheckResponse, PdfIntegrityCheckResponse
from src.contracts.remediation import RemediationListRequest
from src.contracts.run_budget import RunBudget
from src.orchestrators.ingest_file_orchestrator import (
    IngestFileDependencies,
    run_ingest_file,
)
from src.services.state_service import list_remediation_records


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
    check_pdf_eof_fn=None,
    check_pdf_integrity_fn=None,
    download_pdf_to_path_fn=None,
    state_record_fn=None,
    get_source_quarantine_fn=None,
    upsert_source_quarantine_fn=None,
):
    return IngestFileDependencies(
        should_skip=lambda *_args, **_kwargs: False,
        cache_pdf_path=lambda settings, file: (
            f"{settings.cache_dir}/{file.file_id}.pdf"
        ),
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
        download_pdf_to_path=download_pdf_to_path_fn
        or (
            lambda req, _ctx: DriveDownloadToPathResponse(
                schema_version="1.0",
                file=req.file,
                output_path=req.output_path,
                md5=None,
                size=10,
            )
        ),
        check_pdf_eof=check_pdf_eof_fn
        or (
            lambda req, _ctx: PdfEofCheckResponse(
                schema_version="1.0", path=req.path, has_eof=True
            )
        ),
        delete_file=lambda req, _ctx: DeleteFileResponse(
            schema_version="1.0", path=req.path, deleted=True
        ),
        run_report_pipeline=run_report_pipeline_fn,
        state_record=state_record_fn or (lambda *_args, **_kwargs: SimpleNamespace()),
        eof_retry_limit=1,
        check_pdf_integrity=check_pdf_integrity_fn,
        get_source_quarantine=get_source_quarantine_fn,
        upsert_source_quarantine=upsert_source_quarantine_fn,
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
        write_md5_sidecar_fn=lambda request, _ctx: (
            sidecar_writes.append(
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
            )
        ),
    )

    result = run_ingest_file(file, 0, settings, run_context, dependencies)

    assert result.outcome.status == "processed"
    assert pipeline_md5["value"] == "computed-md5"
    assert compute_md5_calls["count"] == 1


def test_missing_eof_after_bounded_download_retries_stops_before_pipeline(
    ingest_settings,
    run_context,
):
    file = _drive_file(md5_checksum=None)
    download_calls = {"count": 0}
    download_budgets = []
    pipeline_calls = {"count": 0}
    state_records = []

    def _file_stat(request, _ctx):
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=False,
            size_bytes=None,
            mtime_utc=None,
            md5=None,
        )

    def _download(req, _ctx):
        download_calls["count"] += 1
        download_budgets.append(req.run_budget)
        return DriveDownloadToPathResponse(
            schema_version="1.0",
            file=req.file,
            output_path=req.output_path,
            md5="source-md5",
            size=10,
        )

    def _run_report_pipeline(current_file, _cache_path, _settings, md5, _ctx):
        del current_file, md5
        pipeline_calls["count"] += 1
        raise AssertionError("report pipeline should not run for malformed PDF")

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=_run_report_pipeline,
        write_md5_sidecar_fn=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            record=None,
            written=False,
            reason="not_called",
        ),
        check_pdf_eof_fn=lambda req, _ctx: PdfEofCheckResponse(
            schema_version="1.0", path=req.path, has_eof=False
        ),
        download_pdf_to_path_fn=_download,
        state_record_fn=lambda request, _ctx: (
            state_records.append(request) or SimpleNamespace()
        ),
    )
    run_budget = RunBudget(
        schema_version="1.0",
        run_id=run_context.run_id,
        publisher_name="",
        usage_db_path=ingest_settings.usage_db_path,
    )
    dependencies = replace(dependencies, run_budget=run_budget)

    result = run_ingest_file(file, 0, ingest_settings, run_context, dependencies)

    assert result.outcome.status == "error"
    assert result.outcome.error == (
        f"Downloaded PDF is missing EOF marker: {ingest_settings.cache_dir}/file-1.pdf"
    )
    assert download_calls["count"] == 2
    assert download_budgets == [run_budget, run_budget]
    assert pipeline_calls["count"] == 0
    assert len(state_records) == 1
    assert state_records[0].state_db == ingest_settings.state_db
    assert state_records[0].file_id == "file-1"
    assert state_records[0].md5 == "source-md5"
    assert state_records[0].last_error == (
        "pdf_download_missing_eof: "
        f"Downloaded PDF is missing EOF marker: {ingest_settings.cache_dir}/file-1.pdf"
    )
    assert state_records[0].text_validation_status == "fail"
    assert state_records[0].text_validation_reason == "pdf_download_missing_eof"


def test_structural_integrity_failure_is_quarantined_before_report_pipeline(
    ingest_settings,
    run_context,
):
    file = _drive_file(md5_checksum="source-md5")
    pipeline_calls = {"count": 0}
    quarantines = []

    def _file_stat(request, _ctx):
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=True,
            size_bytes=100,
            mtime_utc=123.0,
            md5="source-md5" if request.compute_md5 else None,
        )

    def _integrity(request, _ctx):
        return PdfIntegrityCheckResponse(
            schema_version="1.0",
            path=request.path,
            size_bytes=100,
            sha256="a" * 64,
            md5="source-md5",
            validator_version="pdf-integrity-v1",
            has_pdf_header=True,
            has_eof=True,
            parser_opened=False,
            page_count=0,
            failure_code="pdf_parser_open_failed",
            retryable=False,
            validated_at_utc="2026-07-19T10:00:00+00:00",
        )

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=lambda *_args: (
            pipeline_calls.__setitem__("count", pipeline_calls["count"] + 1)
            or _outcome(file, "source-md5")
        ),
        write_md5_sidecar_fn=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            record=None,
            written=False,
            reason="not_called",
        ),
        check_pdf_integrity_fn=_integrity,
        upsert_source_quarantine_fn=lambda request, _ctx: (
            quarantines.append(request.record) or SimpleNamespace(record=request.record)
        ),
    )

    result = run_ingest_file(file, 0, ingest_settings, run_context, dependencies)

    assert result.outcome.status == "error"
    assert pipeline_calls["count"] == 0
    assert len(quarantines) == 1
    assert quarantines[0].status == "active"
    assert quarantines[0].failure_code == "pdf_parser_open_failed"


def test_ingest_file_enables_latest_safe_resume_when_pipeline_accepts_keyword(
    ingest_settings,
    run_context,
):
    settings = replace(ingest_settings, vector_store_keep=True)
    file = _drive_file(md5_checksum="drive-md5")
    captured = {"auto_resume": None}

    def _file_stat(request, _ctx):
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=True,
            size_bytes=10,
            mtime_utc=123.0,
            md5="drive-md5" if request.compute_md5 else None,
        )

    def _run_report_pipeline(
        current_file,
        _cache_path,
        _settings,
        md5,
        _ctx,
        *,
        auto_resume_from_latest_safe=False,
    ):
        captured["auto_resume"] = auto_resume_from_latest_safe
        return _outcome(current_file, md5)

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=_run_report_pipeline,
        write_md5_sidecar_fn=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
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
    assert captured["auto_resume"] is True


def test_ingest_file_records_pipeline_exception_as_terminal_state(
    ingest_settings,
    run_context,
):
    file = _drive_file(md5_checksum="drive-md5")
    state_records = []

    def _file_stat(request, _ctx):
        return FileStatResponse(
            schema_version="1.0",
            path=request.path,
            exists=True,
            size_bytes=10,
            mtime_utc=123.0,
            md5="drive-md5" if request.compute_md5 else None,
        )

    def _run_report_pipeline(*_args, **_kwargs):
        raise ValueError("Validation issue requested an unsupported repair target")

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=_run_report_pipeline,
        write_md5_sidecar_fn=lambda request, _ctx: FileCacheMd5SidecarWriteResponse(
            schema_version="1.0",
            cache_path=request.cache_path,
            sidecar_path=f"{request.cache_path}.md5.json",
            record=None,
            written=False,
            reason="not_called",
        ),
        state_record_fn=lambda request, _ctx: (
            state_records.append(request) or SimpleNamespace()
        ),
    )

    result = run_ingest_file(file, 0, ingest_settings, run_context, dependencies)

    assert result.outcome.status == "error"
    assert result.outcome.md5 == "drive-md5"
    assert state_records[0].file_id == "file-1"
    assert state_records[0].md5 == "drive-md5"
    assert state_records[0].last_error == (
        "ValueError: Validation issue requested an unsupported repair target"
    )
    records = list_remediation_records(
        RemediationListRequest(
            schema_version="1.0",
            state_db=ingest_settings.state_db,
            workflow="ingest_file",
        ),
        run_context,
    ).records
    assert len(records) == 1
    assert records[0].error_code == "ValueError"
    assert records[0].status == "operator_action_required"


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
        run_report_pipeline_fn=lambda current_file, _cache_path, _settings, md5, _ctx: (
            _outcome(current_file, md5)
        ),
        write_md5_sidecar_fn=lambda request, _ctx: (
            sidecar_writes.append(
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
            )
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
