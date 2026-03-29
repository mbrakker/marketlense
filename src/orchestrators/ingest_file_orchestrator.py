from __future__ import annotations

import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional

from src.contracts.drive import DriveDownloadToPathRequest, DriveFile
from src.contracts.files import DeleteFileRequest, FileStatRequest
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.pdf_utils import PdfEofCheckRequest
from src.contracts.run_context import RunContext
from src.contracts.state import StateRecordRequest
from src.utils.logging import child_context, log_event


@dataclass(frozen=True)
class IngestFileDependencies:
    should_skip: Callable[[DriveFile, Optional[str], str, RunContext], bool]
    cache_pdf_path: Callable[[IngestSettings, DriveFile], str]
    md5_sidecar_path: Callable[[str], str]
    load_md5_sidecar: Callable[[str, str, RunContext], Optional[dict]]
    sidecar_md5_for_stat: Callable[
        [dict, Optional[int], Optional[float]], Optional[str]
    ]
    ensure_file_name: Callable[[DriveFile, IngestSettings, RunContext], DriveFile]
    write_md5_sidecar: Callable[
        [str, DriveFile, Optional[str], Optional[int], Optional[float], RunContext],
        None,
    ]
    existing_report_html: Callable[
        [DriveFile, str, IngestSettings, RunContext], Optional[str]
    ]
    run_step_with_retry: Callable[[str, RunContext, Callable[[], Any], int], Any]
    file_stat: Callable[[FileStatRequest, RunContext], Any]
    download_pdf_to_path: Callable[[DriveDownloadToPathRequest, RunContext], Any]
    check_pdf_eof: Callable[[PdfEofCheckRequest, RunContext], Any]
    delete_file: Callable[[DeleteFileRequest, RunContext], Any]
    run_report_pipeline: Callable[
        [DriveFile, str, IngestSettings, Optional[str], RunContext], IngestOutcome
    ]
    state_record: Callable[[StateRecordRequest, RunContext], Any]
    eof_retry_limit: int


@dataclass(frozen=True)
class FileProcessResult:
    index: int
    outcome: IngestOutcome
    processed: int
    had_error: bool


def run_ingest_file(
    file: DriveFile,
    index: int,
    settings: IngestSettings,
    root_ctx: RunContext,
    dependencies: IngestFileDependencies,
    *,
    logger_name: str = "market_lense.ingest_file_orchestrator",
) -> FileProcessResult:
    logger = logging.getLogger(logger_name)
    file_ctx = child_context(root_ctx, task_id=file.file_id)
    display_name = file.name or file.file_id
    cache_path = dependencies.cache_pdf_path(settings, file)
    sidecar_path = dependencies.md5_sidecar_path(cache_path)
    md5 = None
    drive_md5 = file.md5_checksum.strip() if file.md5_checksum else None
    state_checked_md5 = drive_md5
    report_checked_md5 = None

    def _result(
        outcome: IngestOutcome, processed: int = 0, had_error: bool = False
    ) -> FileProcessResult:
        return FileProcessResult(
            index=index, outcome=outcome, processed=processed, had_error=had_error
        )

    try:
        if drive_md5:
            existing_html = dependencies.existing_report_html(
                file, drive_md5, settings, file_ctx
            )
            report_checked_md5 = drive_md5
            if existing_html:
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="report_html_skip",
                        module=logger_name,
                        fields={
                            "file_id": file.file_id,
                            "md5": drive_md5,
                            "html_path": existing_html,
                        },
                    )
                )
                return _result(
                    IngestOutcome(
                        schema_version="1.0",
                        file_id=file.file_id,
                        name=display_name,
                        md5=drive_md5,
                        html_path=existing_html,
                        status="skipped",
                        error="html_exists",
                    )
                )

        cache_hit = False
        cache_reason = ""
        sidecar_used = False
        stat_resp = dependencies.file_stat(
            FileStatRequest(schema_version="1.0", path=cache_path), file_ctx
        )
        if stat_resp.exists:
            sidecar_payload = dependencies.load_md5_sidecar(
                sidecar_path, file.file_id, file_ctx
            )
            md5 = (
                dependencies.sidecar_md5_for_stat(
                    sidecar_payload,
                    stat_resp.size_bytes,
                    stat_resp.mtime_utc,
                )
                if sidecar_payload is not None
                else None
            )
            if md5:
                sidecar_used = True
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="md5_sidecar_hit",
                        module=logger_name,
                        fields={
                            "file_id": file.file_id,
                            "path": sidecar_path,
                            "md5": md5,
                        },
                    )
                )
            else:
                if sidecar_payload:
                    logger.info(
                        log_event(
                            file_ctx,
                            role="orchestrator",
                            event="md5_sidecar_mismatch",
                            module=logger_name,
                            fields={"file_id": file.file_id, "path": sidecar_path},
                        )
                    )
                stat_resp = dependencies.file_stat(
                    FileStatRequest(
                        schema_version="1.0", path=cache_path, compute_md5=True
                    ),
                    file_ctx,
                )
                md5 = stat_resp.md5
                if md5:
                    dependencies.write_md5_sidecar(
                        sidecar_path,
                        file,
                        md5,
                        stat_resp.size_bytes,
                        stat_resp.mtime_utc,
                        file_ctx,
                    )
            if drive_md5 and md5:
                cache_hit = md5 == drive_md5
                if not cache_hit:
                    cache_reason = "md5_mismatch"
            else:
                cache_hit = md5 is not None
                if md5 is None:
                    cache_reason = "md5_unavailable"
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="pdf_cache_hit" if cache_hit else "pdf_cache_miss",
                    module=logger_name,
                    fields={
                        "file_id": file.file_id,
                        "path": cache_path,
                        "md5": md5,
                        "drive_md5": drive_md5 or "",
                        "reason": cache_reason
                        or ("sidecar" if sidecar_used else "hashed"),
                    },
                )
            )
        else:
            cache_reason = "missing"
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="pdf_cache_miss",
                    module=logger_name,
                    fields={
                        "file_id": file.file_id,
                        "path": cache_path,
                        "reason": cache_reason,
                    },
                )
            )

        if not cache_hit:
            dl_req = DriveDownloadToPathRequest(
                schema_version="1.0",
                file=file,
                service_account_path=settings.google_sa_path,
                auth_mode=settings.drive_auth_mode,
                oauth_client_path=settings.google_oauth_client_path,
                oauth_token_path=settings.google_oauth_token_path,
                output_path=cache_path,
            )
            eof_check = None
            attempt = 0
            while True:
                dl_resp = dependencies.run_step_with_retry(
                    "download_pdf",
                    file_ctx,
                    lambda: dependencies.download_pdf_to_path(dl_req, file_ctx),
                    2,
                )
                md5 = dl_resp.md5 or drive_md5
                eof_check = dependencies.check_pdf_eof(
                    PdfEofCheckRequest(schema_version="1.0", path=cache_path),
                    file_ctx,
                )
                if eof_check.has_eof or attempt >= dependencies.eof_retry_limit:
                    break
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="pdf_eof_retry",
                        module=logger_name,
                        fields={
                            "file_id": file.file_id,
                            "path": cache_path,
                            "attempt": attempt + 1,
                        },
                    )
                )
                dependencies.delete_file(
                    DeleteFileRequest(
                        schema_version="1.0", path=cache_path, missing_ok=True
                    ),
                    file_ctx,
                )
                attempt += 1
            if eof_check and not eof_check.has_eof:
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="pdf_missing_eof",
                        module=logger_name,
                        fields={
                            "file_id": file.file_id,
                            "path": cache_path,
                            "proceeding": True,
                        },
                    )
                )
            stat_resp = dependencies.file_stat(
                FileStatRequest(schema_version="1.0", path=cache_path), file_ctx
            )
            dependencies.write_md5_sidecar(
                sidecar_path,
                file,
                md5,
                stat_resp.size_bytes,
                stat_resp.mtime_utc,
                file_ctx,
            )

        if (
            md5
            and md5 != state_checked_md5
            and dependencies.should_skip(file, md5, settings.state_db, file_ctx)
        ):
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="already_processed_skip",
                    module=logger_name,
                    fields={"file_id": file.file_id, "md5": md5},
                )
            )
            return _result(
                IngestOutcome(
                    schema_version="1.0",
                    file_id=file.file_id,
                    name=display_name,
                    md5=md5,
                    html_path=None,
                    status="skipped",
                    error="already_processed",
                )
            )

        if md5 and md5 != report_checked_md5:
            existing_html = dependencies.existing_report_html(
                file, md5, settings, file_ctx
            )
            report_checked_md5 = md5
            if existing_html:
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="report_html_skip",
                        module=logger_name,
                        fields={
                            "file_id": file.file_id,
                            "md5": md5,
                            "html_path": existing_html,
                        },
                    )
                )
                return _result(
                    IngestOutcome(
                        schema_version="1.0",
                        file_id=file.file_id,
                        name=display_name,
                        md5=md5,
                        html_path=existing_html,
                        status="skipped",
                        error="html_exists",
                    )
                )

        file = dependencies.ensure_file_name(file, settings, file_ctx)
        display_name = file.name or file.file_id
        if not md5:
            md5_stat = dependencies.file_stat(
                FileStatRequest(
                    schema_version="1.0", path=cache_path, compute_md5=True
                ),
                file_ctx,
            )
            if md5_stat.exists and md5_stat.md5:
                md5 = md5_stat.md5
                dependencies.write_md5_sidecar(
                    sidecar_path,
                    file,
                    md5,
                    md5_stat.size_bytes,
                    md5_stat.mtime_utc,
                    file_ctx,
                )
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="report_cache_md5_computed",
                        module=logger_name,
                        fields={
                            "file_id": file.file_id,
                            "md5": md5,
                            "path": cache_path,
                        },
                    )
                )
        cache_eligible = bool(md5) and bool(settings.vector_store_keep)
        logger.info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="report_cache_prereq",
                module=logger_name,
                fields={
                    "file_id": file.file_id,
                    "md5_present": bool(md5),
                    "vector_store_keep": bool(settings.vector_store_keep),
                    "eligible": cache_eligible,
                },
            )
        )
        if not settings.vector_store_keep:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="report_cache_disabled_vector_store_keep_false",
                    module=logger_name,
                    fields={"file_id": file.file_id},
                )
            )

        outcome = dependencies.run_step_with_retry(
            "generate_report",
            file_ctx,
            lambda: dependencies.run_report_pipeline(
                file, cache_path, settings, md5, file_ctx
            ),
            0,
        )
        had_errors = outcome.status == "error"
        if outcome.vector_store_id:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="VECTOR_STORE_CREATED",
                    module=logger_name,
                    fields={
                        "file_id": file.file_id,
                        "vector_store_id": outcome.vector_store_id,
                    },
                )
            )
        if outcome.vector_store_status:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="VECTOR_STORE_INDEXED",
                    module=logger_name,
                    fields={
                        "file_id": file.file_id,
                        "vector_store_id": outcome.vector_store_id or "",
                        "status": outcome.vector_store_status,
                        "indexed_at_utc": outcome.indexed_at_utc or "",
                    },
                )
            )
        if outcome.evidence_packs:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="EVIDENCE_READY",
                    module=logger_name,
                    fields={
                        "file_id": file.file_id,
                        "vector_store_id": outcome.vector_store_id or "",
                        "pack_count": len(outcome.evidence_packs),
                    },
                )
            )
        if outcome.status == "error":
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="report_generation_failed",
                    module=logger_name,
                    fields={
                        "file_id": file.file_id,
                        "md5": md5 or "",
                        "error": outcome.error or "",
                        "vector_store_id": outcome.vector_store_id or "",
                    },
                )
            )
            if outcome.doc_map_summary:
                summary = outcome.doc_map_summary
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="doc_map_validation_halt",
                        module=logger_name,
                        fields={
                            "file_id": file.file_id,
                            "md5": md5 or "",
                            "error": outcome.error or "",
                            "has_content": summary.get("has_content"),
                            "sections_count": summary.get("sections_count"),
                            "title_present": summary.get("title_present"),
                            "doc_id_present": summary.get("doc_id_present"),
                            "summary_present": summary.get("summary_present"),
                            "not_found_reason": summary.get("not_found_reason") or "",
                        },
                    )
                )
        last_error = outcome.vector_store_last_error
        if outcome.status == "error" and outcome.error:
            last_error = (
                outcome.error if not last_error else f"{last_error} | {outcome.error}"
            )
        dependencies.state_record(
            StateRecordRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                file_id=file.file_id,
                md5=md5 or "",
                openai_file_id=outcome.openai_file_id or "",
                vector_store_id=outcome.vector_store_id,
                vector_store_status=outcome.vector_store_status,
                indexed_at_utc=outcome.indexed_at_utc,
                last_error=last_error,
                text_validation_status=outcome.text_validation_status,
                text_validation_reason=outcome.text_validation_reason,
                text_validation_pages=outcome.text_validation_pages,
                doc_map_summary=outcome.doc_map_summary,
                ocr_fallback_used=outcome.ocr_fallback_used,
                ocr_pdf_path=outcome.ocr_pdf_path,
            ),
            file_ctx,
        )
        return _result(outcome, processed=1, had_error=had_errors)
    except Exception as exc:
        logger.info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="file_processing_error",
                module=logger_name,
                fields={
                    "file_id": file.file_id,
                    "error": str(exc),
                    "local_path": cache_path,
                    "md5": md5,
                },
            )
        )
        return _result(
            IngestOutcome(
                schema_version="1.0",
                file_id=file.file_id,
                name=display_name,
                md5=None,
                html_path=None,
                status="error",
                error=str(exc),
            ),
            processed=0,
            had_error=True,
        )
