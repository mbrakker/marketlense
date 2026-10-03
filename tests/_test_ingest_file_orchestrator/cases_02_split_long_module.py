# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_ingest_file_orchestrator.py"
)

from ._split_support_test_ingest_file_orchestrator import *  # noqa: F401,F403


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
