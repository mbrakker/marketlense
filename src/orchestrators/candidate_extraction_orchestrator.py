from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional

from src.contracts.candidate_extraction import (
    CandidateExtractOutcome,
    CandidateExtractRequest,
)
from src.contracts.drive import DriveDownloadRequest, DriveListRequest, DriveFile
from src.contracts.files import FileExistsRequest, FileHashRequest, WriteBytesRequest
from src.contracts.ingest import IngestSettings
from src.contracts.pdf_utils import PdfEofCheckRequest
from src.contracts.run_context import RunContext
from src.generators.candidate_extraction_generator import generate_candidate_pack
from src.services.drive_service import download_pdf, list_pdfs
from src.services.file_service import file_exists, file_md5, write_bytes
from src.services.pdf_service import check_pdf_eof
from src.orchestrators.retry_orchestrator import run_step_with_default_policy
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.path_utils import safe_pdf_name
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.candidate_extraction_orchestrator")


@dataclass(frozen=True)
class CandidateExtractionDependencies:
    list_pdfs: Callable[[DriveListRequest, RunContext], Iterable[DriveFile]]
    download_pdf: Callable[[DriveDownloadRequest, RunContext], Any]
    file_exists: Callable[[FileExistsRequest, RunContext], Any]
    file_md5: Callable[[FileHashRequest, RunContext], Any]
    write_bytes: Callable[[WriteBytesRequest, RunContext], Any]
    check_pdf_eof: Callable[[PdfEofCheckRequest, RunContext], Any]
    generate_candidate_pack: Callable[[CandidateExtractRequest, RunContext], Any]
    sleep_fn: Callable[[float], None]

    @classmethod
    def default(cls) -> "CandidateExtractionDependencies":
        return cls(
            list_pdfs=list_pdfs,
            download_pdf=download_pdf,
            file_exists=file_exists,
            file_md5=file_md5,
            write_bytes=write_bytes,
            check_pdf_eof=check_pdf_eof,
            generate_candidate_pack=generate_candidate_pack,
            sleep_fn=time.sleep,
        )


def _slugify_pdf_name(pdf_path: str) -> str:
    return slugify(Path(pdf_path).name)


def _resolve_report_name(file: DriveFile, pdf_path: str | None = None) -> str:
    if file.name:
        return slugify(file.name)
    if pdf_path:
        return _slugify_pdf_name(pdf_path)
    return file.file_id


def _run_step_with_retry(
    step_name: str,
    ctx: RunContext,
    func,
    dependencies: CandidateExtractionDependencies,
    retries: int = 1,
):
    return run_step_with_default_policy(
        step_name=step_name,
        operation=func,
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        retries=retries,
        include_error_text=True,
        sleep_fn=dependencies.sleep_fn,
    )


def _download_if_needed(
    file: DriveFile,
    settings: IngestSettings,
    ctx: RunContext,
    dependencies: CandidateExtractionDependencies,
) -> tuple[str, Optional[str]]:
    cache_name = safe_pdf_name(file.name or f"{file.file_id}.pdf")
    cache_path = str(Path(settings.cache_dir) / cache_name)
    md5 = None
    exists_resp = dependencies.file_exists(
        FileExistsRequest(schema_version="1.0", path=cache_path), ctx
    )
    if exists_resp.exists and file.md5_checksum:
        md5_resp = dependencies.file_md5(
            FileHashRequest(schema_version="1.0", path=cache_path), ctx
        )
        if md5_resp.md5 == file.md5_checksum:
            md5 = md5_resp.md5
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="pdf_cache_hit",
                    module=logger.name,
                    fields={"file_id": file.file_id, "path": cache_path, "md5": md5},
                )
            )
            return cache_path, md5

    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="pdf_cache_miss",
            module=logger.name,
            fields={"file_id": file.file_id, "path": cache_path},
        )
    )
    dl_req = DriveDownloadRequest(
        schema_version="1.0", file=file, service_account_path=settings.google_sa_path
    )
    dl_resp = _run_step_with_retry(
        "download_pdf",
        ctx,
        lambda: dependencies.download_pdf(dl_req, ctx),
        dependencies,
    )
    write_resp = dependencies.write_bytes(
        WriteBytesRequest(
            schema_version="1.0", path=cache_path, content=dl_resp.content
        ),
        ctx,
    )
    md5 = write_resp.md5
    eof_check = dependencies.check_pdf_eof(
        PdfEofCheckRequest(schema_version="1.0", path=cache_path), ctx
    )
    if not eof_check.has_eof:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="pdf_missing_eof",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "path": cache_path,
                    "proceeding": True,
                },
            )
        )
    return cache_path, md5


def run_candidate_extraction(
    settings: IngestSettings,
    *,
    folder_id: Optional[str] = None,
    limit: Optional[int] = None,
    file_id: Optional[str] = None,
    pdf_path: Optional[str] = None,
    report_id: Optional[str] = None,
    ctx: Optional[RunContext] = None,
    dependencies: Optional[CandidateExtractionDependencies] = None,
) -> List[CandidateExtractOutcome]:
    deps = dependencies or CandidateExtractionDependencies.default()
    root_ctx = ctx or new_run_context()
    outcomes: List[CandidateExtractOutcome] = []

    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="candidate_extract_start",
            module=logger.name,
            fields={
                "folder_id": folder_id or settings.gdrive_folder_id,
                "limit": limit,
                "file_id": file_id or "",
                "pdf_path": pdf_path or "",
            },
        )
    )

    if pdf_path:
        file_ctx = child_context(root_ctx, task_id="candidate_extract_local")
        name = _slugify_pdf_name(pdf_path)
        exists_resp = deps.file_exists(
            FileExistsRequest(schema_version="1.0", path=pdf_path), file_ctx
        )
        if not exists_resp.exists:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="candidate_extract_failed",
                    module=logger.name,
                    fields={"pdf_path": pdf_path, "error": "file_not_found"},
                )
            )
            outcomes.append(
                CandidateExtractOutcome(
                    schema_version="1.0",
                    report_id=report_id or name,
                    report_name=name,
                    pdf_path=pdf_path,
                    candidates_path="",
                    candidate_count=0,
                    chart_count=0,
                    table_count=0,
                    crop_count=0,
                    crop_paths=[],
                    error="file_not_found",
                )
            )
            return outcomes
        md5_resp = deps.file_md5(
            FileHashRequest(schema_version="1.0", path=pdf_path), file_ctx
        )
        resolved_report_id = report_id or f"{name}-{md5_resp.md5[:8]}"
        try:
            outcome = deps.generate_candidate_pack(
                CandidateExtractRequest(
                    schema_version="1.0",
                    report_id=resolved_report_id,
                    pdf_path=pdf_path,
                    output_dir=settings.output_dir,
                    report_name=name,
                ),
                file_ctx,
            )
            outcomes.append(outcome)
        except Exception as exc:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="candidate_extract_failed",
                    module=logger.name,
                    fields={"pdf_path": pdf_path, "error": str(exc)},
                )
            )
            outcomes.append(
                CandidateExtractOutcome(
                    schema_version="1.0",
                    report_id=resolved_report_id,
                    report_name=name,
                    pdf_path=pdf_path,
                    candidates_path="",
                    candidate_count=0,
                    chart_count=0,
                    table_count=0,
                    crop_count=0,
                    crop_paths=[],
                    error=str(exc),
                )
            )
        return outcomes

    max_n = limit if limit is not None else settings.batch_limit
    list_req = DriveListRequest(
        schema_version="1.0",
        folder_id=folder_id or settings.gdrive_folder_id,
        service_account_path=settings.google_sa_path,
        page_size=min(max_n, 1000) if limit is not None else None,
        order_by="modifiedTime desc" if limit is not None else None,
        list_mode="full",
        supports_all_drives=settings.drive_supports_all_drives,
        include_items_from_all_drives=settings.drive_include_items_from_all_drives,
        drive_id=settings.drive_id,
    )
    processed = 0

    for file in deps.list_pdfs(list_req, root_ctx):
        if processed >= max_n:
            break
        if file_id and file.file_id != file_id:
            continue
        file_ctx = child_context(root_ctx, task_id=file.file_id)
        try:
            cache_path, _ = _download_if_needed(file, settings, file_ctx, deps)
            report_name = _resolve_report_name(file, cache_path)
            outcome = deps.generate_candidate_pack(
                CandidateExtractRequest(
                    schema_version="1.0",
                    report_id=file.file_id,
                    pdf_path=cache_path,
                    output_dir=settings.output_dir,
                    report_name=report_name,
                ),
                file_ctx,
            )
            outcomes.append(outcome)
            processed += 1
        except Exception as exc:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="candidate_extract_failed",
                    module=logger.name,
                    fields={"file_id": file.file_id, "error": str(exc)},
                )
            )
            outcomes.append(
                CandidateExtractOutcome(
                    schema_version="1.0",
                    report_id=file.file_id,
                    report_name=file.name or file.file_id,
                    pdf_path="",
                    candidates_path="",
                    candidate_count=0,
                    chart_count=0,
                    table_count=0,
                    crop_count=0,
                    crop_paths=[],
                    error=str(exc),
                )
            )
            processed += 1

    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="candidate_extract_complete",
            module=logger.name,
            fields={"processed": processed},
        )
    )
    return outcomes
