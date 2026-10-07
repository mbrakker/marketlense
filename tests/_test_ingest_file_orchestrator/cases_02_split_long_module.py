# ruff: noqa: F401,F403,F405
from __future__ import annotations

from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_ingest_file_orchestrator.py"
)

import hashlib
import json
from pathlib import Path

import pytest

from src.services import file_cache_service, file_service

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


@pytest.mark.parametrize(
    ("sidecar_file_id", "sidecar_md5", "expected_hash_calls"),
    [
        pytest.param("file-1", "source", 0, id="valid-source-bound-sidecar"),
        pytest.param("foreign-file", "foreign", 1, id="foreign-sidecar-rehashed"),
    ],
)
def test_ingest_cache_uses_only_source_bound_sidecar(
    tmp_path,
    ingest_settings,
    run_context,
    sidecar_file_id: str,
    sidecar_md5: str,
    expected_hash_calls: int,
) -> None:
    settings = replace(
        ingest_settings,
        cache_dir=str(tmp_path / "cache"),
        output_dir=str(tmp_path / "out"),
        vector_store_keep=True,
    )
    cache_path = Path(settings.cache_dir) / "file-1.pdf"
    cache_path.parent.mkdir(parents=True, exist_ok=True)
    pdf_bytes = b"%PDF-1.4\n%%EOF\n"
    cache_path.write_bytes(pdf_bytes)
    source_md5 = hashlib.md5(pdf_bytes).hexdigest()
    cache_stat = cache_path.stat()
    sidecar_md5_value = source_md5 if sidecar_md5 == "source" else "f" * 32
    sidecar_path = Path(f"{cache_path}.md5.json")
    sidecar_path.write_text(
        json.dumps(
            {
                "schema_version": "2.0",
                "file_id": sidecar_file_id,
                "name": "file-1.pdf",
                "md5": sidecar_md5_value,
                "size_bytes": cache_stat.st_size,
                "mtime_ns": cache_stat.st_mtime_ns,
            }
        ),
        encoding="utf-8",
    )

    hash_calls = []
    download_calls = []

    def _file_stat(request, ctx):
        if request.compute_md5:
            hash_calls.append(request.path)
        return file_service.file_stat(request, ctx)

    dependencies = _base_dependencies(
        file_stat_fn=_file_stat,
        run_report_pipeline_fn=lambda current_file, _cache_path, _settings, md5, _ctx: (
            _outcome(current_file, md5)
        ),
        write_md5_sidecar_fn=file_cache_service.write_md5_sidecar,
        download_pdf_to_path_fn=lambda request, _ctx: (
            download_calls.append(request.output_path)
            or DriveDownloadToPathResponse(
                schema_version="1.0",
                file=request.file,
                output_path=request.output_path,
                md5=None,
                size=len(pdf_bytes),
            )
        ),
    )
    dependencies = replace(
        dependencies,
        resolve_md5_sidecar=file_cache_service.resolve_md5_sidecar,
    )

    result = run_ingest_file(
        _drive_file(md5_checksum=source_md5), 0, settings, run_context, dependencies
    )

    assert result.outcome.status == "processed"
    assert result.outcome.md5 == source_md5
    assert len(hash_calls) == expected_hash_calls
    assert download_calls == []
    repaired_sidecar = json.loads(sidecar_path.read_text(encoding="utf-8"))
    assert repaired_sidecar["file_id"] == "file-1"
    assert repaired_sidecar["md5"] == source_md5
