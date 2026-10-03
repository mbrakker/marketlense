# ruff: noqa: F401,F403,F405
from __future__ import annotations
from pathlib import Path as _SplitPath

__file__ = str(
    _SplitPath(__file__).resolve().parent.parent / "test_ingest_file_orchestrator.py"
)

import json
import sqlite3
from dataclasses import replace
from datetime import UTC, datetime, timedelta
from pathlib import Path
from types import SimpleNamespace
from src.contracts.drive import DriveDownloadToPathResponse, DriveFile
from src.contracts.file_cache import (
    FileCacheMd5SidecarResolveResponse,
    FileCacheMd5SidecarWriteResponse,
)
from src.contracts.files import DeleteFileResponse, FileStatResponse
from src.contracts.ingest import IngestOutcome, RetainedReportPackage
from src.contracts.pdf_utils import PdfEofCheckResponse, PdfIntegrityCheckResponse
from src.contracts.remediation import RemediationListRequest
from src.contracts.run_budget import RunBudget
from src.contracts.validation import ValidationReport
from src.generators.publish_readiness_generator import (
    evaluate_publish_readiness,
    publish_readiness_payload,
)
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
    read_text_fn=None,
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
        read_text=read_text_fn,
        check_pdf_integrity=check_pdf_integrity_fn,
        get_source_quarantine=get_source_quarantine_fn,
        upsert_source_quarantine=upsert_source_quarantine_fn,
    )


__all__ = [name for name in globals() if not name.startswith("__")]
