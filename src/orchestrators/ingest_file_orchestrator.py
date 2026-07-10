from __future__ import annotations

import inspect
import logging
from dataclasses import dataclass
from typing import Any, Callable, Optional, Protocol, cast

from src.contracts.file_cache import (
    FileCacheMd5SidecarResolveRequest,
    FileCacheMd5SidecarResolveResponse,
    FileCacheMd5SidecarWriteRequest,
    FileCacheMd5SidecarWriteResponse,
)
from src.contracts.drive import DriveDownloadToPathRequest, DriveFile
from src.contracts.files import DeleteFileRequest, FileStatRequest
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.pdf_utils import PdfEofCheckRequest
from src.contracts.run_context import RunContext
from src.contracts.state import StateRecordRequest
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event


def _accepts_keyword(callable_obj: Callable[..., Any], keyword: str) -> bool:
    try:
        parameters = inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return False
    return keyword in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


class _LatestSafeReportPipeline(Protocol):
    def __call__(
        self,
        file: DriveFile,
        cache_path: str,
        settings: IngestSettings,
        md5: str | None,
        ctx: RunContext,
        *,
        auto_resume_from_latest_safe: bool,
    ) -> IngestOutcome: ...


def _run_report_pipeline_latest_safe(
    dependencies: IngestFileDependencies,
    file: DriveFile,
    cache_path: str,
    settings: IngestSettings,
    md5: str | None,
    ctx: RunContext,
) -> IngestOutcome:
    if _accepts_keyword(
        dependencies.run_report_pipeline,
        "auto_resume_from_latest_safe",
    ):
        latest_safe_pipeline = cast(
            _LatestSafeReportPipeline,
            dependencies.run_report_pipeline,
        )
        return latest_safe_pipeline(
            file,
            cache_path,
            settings,
            md5,
            ctx,
            auto_resume_from_latest_safe=True,
        )
    return dependencies.run_report_pipeline(file, cache_path, settings, md5, ctx)


@dataclass(frozen=True)
class IngestFileDependencies:
    should_skip: Callable[[DriveFile, Optional[str], str, RunContext], bool]
    cache_pdf_path: Callable[[IngestSettings, DriveFile], str]
    resolve_md5_sidecar: Callable[
        [FileCacheMd5SidecarResolveRequest, RunContext],
        FileCacheMd5SidecarResolveResponse,
    ]
    ensure_file_name: Callable[[DriveFile, IngestSettings, RunContext], DriveFile]
    write_md5_sidecar: Callable[
        [FileCacheMd5SidecarWriteRequest, RunContext],
        FileCacheMd5SidecarWriteResponse,
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
    bypass_existing_report_html: bool = False


@dataclass(frozen=True)
class FileProcessResult:
    index: int
    outcome: IngestOutcome
    processed: int
    had_error: bool


@dataclass
class _IngestFileRuntime:
    file: DriveFile
    display_name: str
    cache_path: str
    md5: str | None
    drive_md5: str | None
    state_checked_md5: str | None
    report_checked_md5: str | None


def _file_result(
    *,
    index: int,
    outcome: IngestOutcome,
    processed: int = 0,
    had_error: bool = False,
) -> FileProcessResult:
    return FileProcessResult(
        index=index,
        outcome=outcome,
        processed=processed,
        had_error=had_error,
    )


def _skip_result(
    *,
    index: int,
    file: DriveFile,
    display_name: str,
    md5: str | None,
    html_path: str | None,
    error: str,
) -> FileProcessResult:
    return _file_result(
        index=index,
        outcome=IngestOutcome(
            schema_version="1.0",
            file_id=file.file_id,
            name=display_name,
            md5=md5,
            html_path=html_path,
            status="skipped",
            error=error,
        ),
    )


def _maybe_skip_existing_report_html(
    runtime: _IngestFileRuntime,
    *,
    index: int,
    settings: IngestSettings,
    dependencies: IngestFileDependencies,
    file_ctx: RunContext,
    logger_name: str,
) -> FileProcessResult | None:
    if not runtime.md5:
        return None
    if dependencies.bypass_existing_report_html:
        logging.getLogger(logger_name).info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="report_html_cache_bypassed",
                module=logger_name,
                fields={
                    "file_id": runtime.file.file_id,
                    "md5": runtime.md5,
                    "reason": "force_report_cards",
                },
            )
        )
        return None
    existing_html = dependencies.existing_report_html(
        runtime.file,
        runtime.md5,
        settings,
        file_ctx,
    )
    runtime.report_checked_md5 = runtime.md5
    if not existing_html:
        return None
    logging.getLogger(logger_name).info(
        log_event(
            file_ctx,
            role="orchestrator",
            event="report_html_skip",
            module=logger_name,
            fields={
                "file_id": runtime.file.file_id,
                "md5": runtime.md5,
                "html_path": existing_html,
            },
        )
    )
    return _skip_result(
        index=index,
        file=runtime.file,
        display_name=runtime.display_name,
        md5=runtime.md5,
        html_path=existing_html,
        error="html_exists",
    )


def _resolve_cached_pdf(
    runtime: _IngestFileRuntime,
    *,
    dependencies: IngestFileDependencies,
    file_ctx: RunContext,
    logger_name: str,
) -> bool:
    logger = logging.getLogger(logger_name)
    cache_hit = False
    cache_reason = ""
    sidecar_used = False
    stat_resp = dependencies.file_stat(
        FileStatRequest(schema_version="1.0", path=runtime.cache_path),
        file_ctx,
    )
    if not stat_resp.exists:
        logger.info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="pdf_cache_miss",
                module=logger_name,
                fields={
                    "file_id": runtime.file.file_id,
                    "path": runtime.cache_path,
                    "reason": "missing",
                },
            )
        )
        return False

    sidecar_response = dependencies.resolve_md5_sidecar(
        FileCacheMd5SidecarResolveRequest(
            schema_version="1.0",
            cache_path=runtime.cache_path,
            file_id=runtime.file.file_id,
            size_bytes=stat_resp.size_bytes,
            mtime_utc=stat_resp.mtime_utc,
        ),
        file_ctx,
    )
    runtime.md5 = sidecar_response.resolved_md5
    if runtime.md5:
        sidecar_used = True
        logger.info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="md5_sidecar_hit",
                module=logger_name,
                fields={
                    "file_id": runtime.file.file_id,
                    "path": sidecar_response.sidecar_path,
                    "md5": runtime.md5,
                },
            )
        )
    else:
        if sidecar_response.sidecar_exists:
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="md5_sidecar_mismatch",
                    module=logger_name,
                    fields={
                        "file_id": runtime.file.file_id,
                        "path": sidecar_response.sidecar_path,
                        "reason": sidecar_response.reason,
                    },
                )
            )
        stat_resp = dependencies.file_stat(
            FileStatRequest(
                schema_version="1.0",
                path=runtime.cache_path,
                compute_md5=True,
            ),
            file_ctx,
        )
        runtime.md5 = stat_resp.md5
        if runtime.md5:
            dependencies.write_md5_sidecar(
                FileCacheMd5SidecarWriteRequest(
                    schema_version="1.0",
                    cache_path=runtime.cache_path,
                    file_id=runtime.file.file_id,
                    file_name=runtime.file.name,
                    md5=runtime.md5,
                    size_bytes=stat_resp.size_bytes,
                    mtime_utc=stat_resp.mtime_utc,
                ),
                file_ctx,
            )
    if runtime.drive_md5 and runtime.md5:
        cache_hit = runtime.md5 == runtime.drive_md5
        if not cache_hit:
            cache_reason = "md5_mismatch"
    else:
        cache_hit = runtime.md5 is not None
        if runtime.md5 is None:
            cache_reason = "md5_unavailable"
    logger.info(
        log_event(
            file_ctx,
            role="orchestrator",
            event="pdf_cache_hit" if cache_hit else "pdf_cache_miss",
            module=logger_name,
            fields={
                "file_id": runtime.file.file_id,
                "path": runtime.cache_path,
                "md5": runtime.md5,
                "drive_md5": runtime.drive_md5 or "",
                "reason": cache_reason or ("sidecar" if sidecar_used else "hashed"),
            },
        )
    )
    return cache_hit


def _download_pdf_for_processing(
    runtime: _IngestFileRuntime,
    *,
    settings: IngestSettings,
    dependencies: IngestFileDependencies,
    file_ctx: RunContext,
    logger_name: str,
) -> None:
    logger = logging.getLogger(logger_name)
    dl_req = DriveDownloadToPathRequest(
        schema_version="1.0",
        file=runtime.file,
        service_account_path=settings.google_sa_path,
        auth_mode=settings.drive_auth_mode,
        oauth_client_path=settings.google_oauth_client_path,
        oauth_token_path=settings.google_oauth_token_path,
        output_path=runtime.cache_path,
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
        runtime.md5 = dl_resp.md5 or runtime.drive_md5
        eof_check = dependencies.check_pdf_eof(
            PdfEofCheckRequest(schema_version="1.0", path=runtime.cache_path),
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
                    "file_id": runtime.file.file_id,
                    "path": runtime.cache_path,
                    "attempt": attempt + 1,
                },
            )
        )
        dependencies.delete_file(
            DeleteFileRequest(
                schema_version="1.0",
                path=runtime.cache_path,
                missing_ok=True,
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
                    "file_id": runtime.file.file_id,
                    "path": runtime.cache_path,
                    "proceeding": False,
                },
            )
        )
        raise AppError(
            code="pdf_download_missing_eof",
            message=f"Downloaded PDF is missing EOF marker: {runtime.cache_path}",
            retryable=False,
            context={
                "file_id": runtime.file.file_id,
                "path": runtime.cache_path,
                "attempts": attempt + 1,
            },
        )
    stat_resp = dependencies.file_stat(
        FileStatRequest(schema_version="1.0", path=runtime.cache_path),
        file_ctx,
    )
    dependencies.write_md5_sidecar(
        FileCacheMd5SidecarWriteRequest(
            schema_version="1.0",
            cache_path=runtime.cache_path,
            file_id=runtime.file.file_id,
            file_name=runtime.file.name,
            md5=runtime.md5,
            size_bytes=stat_resp.size_bytes,
            mtime_utc=stat_resp.mtime_utc,
        ),
        file_ctx,
    )


def _refresh_cached_pdf_when_invalid(
    runtime: _IngestFileRuntime,
    *,
    settings: IngestSettings,
    dependencies: IngestFileDependencies,
    file_ctx: RunContext,
    logger_name: str,
) -> None:
    eof_check = dependencies.check_pdf_eof(
        PdfEofCheckRequest(schema_version="1.0", path=runtime.cache_path),
        file_ctx,
    )
    if eof_check.has_eof:
        return
    logging.getLogger(logger_name).info(
        log_event(
            file_ctx,
            role="orchestrator",
            event="pdf_cache_invalid_redownload",
            module=logger_name,
            fields={
                "file_id": runtime.file.file_id,
                "path": runtime.cache_path,
                "reason": "missing_eof",
            },
        )
    )
    dependencies.delete_file(
        DeleteFileRequest(
            schema_version="1.0",
            path=runtime.cache_path,
            missing_ok=True,
        ),
        file_ctx,
    )
    _download_pdf_for_processing(
        runtime,
        settings=settings,
        dependencies=dependencies,
        file_ctx=file_ctx,
        logger_name=logger_name,
    )


def _ensure_runtime_md5(
    runtime: _IngestFileRuntime,
    *,
    settings: IngestSettings,
    dependencies: IngestFileDependencies,
    file_ctx: RunContext,
    logger_name: str,
) -> None:
    if runtime.md5:
        return
    md5_stat = dependencies.file_stat(
        FileStatRequest(
            schema_version="1.0",
            path=runtime.cache_path,
            compute_md5=True,
        ),
        file_ctx,
    )
    if not (md5_stat.exists and md5_stat.md5):
        return
    runtime.md5 = md5_stat.md5
    dependencies.write_md5_sidecar(
        FileCacheMd5SidecarWriteRequest(
            schema_version="1.0",
            cache_path=runtime.cache_path,
            file_id=runtime.file.file_id,
            file_name=runtime.file.name,
            md5=runtime.md5,
            size_bytes=md5_stat.size_bytes,
            mtime_utc=md5_stat.mtime_utc,
        ),
        file_ctx,
    )
    logging.getLogger(logger_name).info(
        log_event(
            file_ctx,
            role="orchestrator",
            event="report_cache_md5_computed",
            module=logger_name,
            fields={
                "file_id": runtime.file.file_id,
                "md5": runtime.md5,
                "path": runtime.cache_path,
            },
        )
    )


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
    runtime = _IngestFileRuntime(
        file=file,
        display_name=file.name or file.file_id,
        cache_path=dependencies.cache_pdf_path(settings, file),
        md5=None,
        drive_md5=file.md5_checksum.strip() if file.md5_checksum else None,
        state_checked_md5=file.md5_checksum.strip() if file.md5_checksum else None,
        report_checked_md5=None,
    )

    try:
        runtime.md5 = runtime.drive_md5
        skipped = _maybe_skip_existing_report_html(
            runtime,
            index=index,
            settings=settings,
            dependencies=dependencies,
            file_ctx=file_ctx,
            logger_name=logger_name,
        )
        if skipped is not None:
            return skipped

        runtime.md5 = None
        cache_hit = _resolve_cached_pdf(
            runtime,
            dependencies=dependencies,
            file_ctx=file_ctx,
            logger_name=logger_name,
        )
        if not cache_hit:
            _download_pdf_for_processing(
                runtime,
                settings=settings,
                dependencies=dependencies,
                file_ctx=file_ctx,
                logger_name=logger_name,
            )
        else:
            _refresh_cached_pdf_when_invalid(
                runtime,
                settings=settings,
                dependencies=dependencies,
                file_ctx=file_ctx,
                logger_name=logger_name,
            )

        if (
            runtime.md5
            and runtime.md5 != runtime.state_checked_md5
            and dependencies.should_skip(
                runtime.file,
                runtime.md5,
                settings.state_db,
                file_ctx,
            )
        ):
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="already_processed_skip",
                    module=logger_name,
                    fields={"file_id": runtime.file.file_id, "md5": runtime.md5},
                )
            )
            return _skip_result(
                index=index,
                file=runtime.file,
                display_name=runtime.display_name,
                md5=runtime.md5,
                html_path=None,
                error="already_processed",
            )

        skipped = _maybe_skip_existing_report_html(
            runtime,
            index=index,
            settings=settings,
            dependencies=dependencies,
            file_ctx=file_ctx,
            logger_name=logger_name,
        )
        if skipped is not None and runtime.md5 != runtime.drive_md5:
            return skipped

        runtime.file = dependencies.ensure_file_name(runtime.file, settings, file_ctx)
        runtime.display_name = runtime.file.name or runtime.file.file_id
        _ensure_runtime_md5(
            runtime,
            settings=settings,
            dependencies=dependencies,
            file_ctx=file_ctx,
            logger_name=logger_name,
        )
        cache_eligible = bool(runtime.md5) and bool(settings.vector_store_keep)
        logger.info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="report_cache_prereq",
                module=logger_name,
                fields={
                    "file_id": runtime.file.file_id,
                    "md5_present": bool(runtime.md5),
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
                    fields={"file_id": runtime.file.file_id},
                )
            )

        outcome = dependencies.run_step_with_retry(
            "generate_report",
            file_ctx,
            lambda: _run_report_pipeline_latest_safe(
                dependencies,
                runtime.file,
                runtime.cache_path,
                settings,
                runtime.md5,
                file_ctx,
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
                        "file_id": runtime.file.file_id,
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
                        "file_id": runtime.file.file_id,
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
                        "file_id": runtime.file.file_id,
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
                        "file_id": runtime.file.file_id,
                        "md5": runtime.md5 or "",
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
                            "file_id": runtime.file.file_id,
                            "md5": runtime.md5 or "",
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
                file_id=runtime.file.file_id,
                md5=runtime.md5 or "",
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
        return _file_result(
            index=index,
            outcome=outcome,
            processed=1,
            had_error=had_errors,
        )
    except Exception as exc:
        logger.info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="file_processing_error",
                module=logger_name,
                fields={
                    "file_id": runtime.file.file_id,
                    "error": str(exc),
                    "local_path": runtime.cache_path,
                    "md5": runtime.md5,
                },
            )
        )
        return _file_result(
            index=index,
            outcome=IngestOutcome(
                schema_version="1.0",
                file_id=runtime.file.file_id,
                name=runtime.display_name,
                md5=None,
                html_path=None,
                status="error",
                error=str(exc),
            ),
            processed=0,
            had_error=True,
        )
