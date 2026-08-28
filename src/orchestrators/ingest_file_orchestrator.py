from __future__ import annotations

import inspect
import json
import logging
from dataclasses import dataclass, replace
from datetime import UTC, datetime
from pathlib import Path
from typing import Any, Callable, Optional

from src.contracts.drive import DriveDownloadToPathRequest, DriveFile
from src.contracts.file_cache import (
    FileCacheMd5SidecarResolveRequest,
    FileCacheMd5SidecarResolveResponse,
    FileCacheMd5SidecarWriteRequest,
    FileCacheMd5SidecarWriteResponse,
)
from src.contracts.files import DeleteFileRequest, FileStatRequest, ReadTextRequest
from src.contracts.ingest import IngestOutcome, IngestSettings, RetainedReportPackage
from src.contracts.pdf_utils import PdfEofCheckRequest, PdfIntegrityCheckRequest
from src.contracts.publish_readiness import PublishReadinessRefreshPlan
from src.contracts.report_store import (
    ReportSourceReuseTelemetryRecord,
    ReportSourceReuseTelemetryRecordRequest,
)
from src.contracts.remediation import RemediationArtifactReference
from src.contracts.run_budget import RunBudget
from src.contracts.run_context import RunContext
from src.contracts.state import (
    SourceQuarantineGetRequest,
    SourceQuarantineRecord,
    SourceQuarantineUpsertRequest,
    StateRecordRequest,
)
from src.generators.publish_readiness_generator import (
    parse_publish_readiness_payload,
    plan_publish_readiness_refresh,
)
from src.orchestrators._report_analysis_orchestrator.manifest import (
    record_validation_manifest_stage,
)
from src.orchestrators.remediation_orchestrator import record_workflow_failure
from src.services.report_store_service import record_report_source_reuse_telemetry
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


def _run_report_pipeline_latest_safe(
    dependencies: IngestFileDependencies,
    file: DriveFile,
    cache_path: str,
    settings: IngestSettings,
    md5: str | None,
    ctx: RunContext,
    resume_from_stage: str | None = None,
    readiness_refresh_plan: PublishReadinessRefreshPlan | None = None,
    refresh_telemetry_path: str = "",
) -> IngestOutcome:
    accepts_resume_stage = _accepts_keyword(
        dependencies.run_report_pipeline,
        "resume_from_stage",
    )
    accepts_auto_resume = _accepts_keyword(
        dependencies.run_report_pipeline,
        "auto_resume_from_latest_safe",
    )
    arguments: dict[str, object] = {}
    if accepts_auto_resume:
        arguments["auto_resume_from_latest_safe"] = not bool(resume_from_stage)
    if accepts_resume_stage:
        arguments["resume_from_stage"] = resume_from_stage
    if readiness_refresh_plan is not None:
        refresh_arguments = {
            "execution_plan_mode": "enforce",
            "recovery_execution_intent": readiness_refresh_plan.execution_intent,
            "recovery_invalidations": readiness_refresh_plan.forced_invalidations,
            "readiness_refresh_plan": readiness_refresh_plan,
            "refresh_telemetry_path": refresh_telemetry_path,
        }
        for name, value in refresh_arguments.items():
            if _accepts_keyword(dependencies.run_report_pipeline, name):
                arguments[name] = value
    return dependencies.run_report_pipeline(
        file,
        cache_path,
        settings,
        md5,
        ctx,
        **arguments,
    )


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
        [DriveFile, str, IngestSettings, RunContext], Optional[str | RetainedReportPackage]
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
    check_pdf_integrity: (
        Callable[[PdfIntegrityCheckRequest, RunContext], Any] | None
    ) = None
    get_source_quarantine: (
        Callable[[SourceQuarantineGetRequest, RunContext], Any] | None
    ) = None
    upsert_source_quarantine: (
        Callable[[SourceQuarantineUpsertRequest, RunContext], Any] | None
    ) = None
    quarantine_enabled: bool = True
    run_budget: RunBudget | None = None
    read_text: Callable[[ReadTextRequest, RunContext], Any] | None = None


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
    retained_package: RetainedReportPackage | None = None
    readiness_refresh_required: bool = False
    readiness_refresh_plan: PublishReadinessRefreshPlan | None = None
    readiness_refresh_telemetry_path: str = ""


def _record_ingest_file_failure(
    *,
    runtime: _IngestFileRuntime,
    settings: IngestSettings,
    error: Exception,
    ctx: RunContext,
) -> None:
    record_workflow_failure(
        state_db=settings.state_db,
        workflow="ingest_file",
        stage="file_processing",
        operation="run_report_pipeline",
        error=error,
        ctx=ctx,
        input_checksum=runtime.md5 or runtime.drive_md5 or runtime.file.file_id,
        report_id=runtime.file.file_id,
        source_id=runtime.cache_path,
        reusable_artifacts=[
            RemediationArtifactReference(
                schema_version="1.0",
                name="cached_pdf",
                reference=runtime.cache_path,
            )
        ]
        if runtime.cache_path
        else [],
    )


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
    publish_readiness_status: str | None = None,
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
            publish_readiness_status=publish_readiness_status,
        ),
    )


def _existing_publish_readiness_refresh_plan(
    html_path: str,
    *,
    report_id: str,
    dependencies: IngestFileDependencies,
    file_ctx: RunContext,
) -> PublishReadinessRefreshPlan:
    """Read and classify the canonical retained decision without re-evaluation."""
    if dependencies.read_text is None:
        return plan_publish_readiness_refresh(
            report_id=report_id,
            readiness=None,
            final_html="",
            configuration_hash=file_ctx.configuration_hash,
            policy_hash=file_ctx.policy_hash,
            producer_revision=file_ctx.producer_commit_sha,
            evaluated_at_utc=datetime.now(UTC),
        )
    readiness_path = (
        Path(html_path).with_suffix("") / "report_analysis" / "publish_readiness.json"
    )
    payload: object = None
    final_html = ""
    try:
        payload = json.loads(
            dependencies.read_text(
                ReadTextRequest(schema_version="1.0", path=str(readiness_path)),
                file_ctx,
            ).content
        )
    except (AppError, OSError, TypeError, ValueError):
        payload = None
    try:
        final_html = dependencies.read_text(
            ReadTextRequest(schema_version="1.0", path=html_path), file_ctx
        ).content
    except (AppError, OSError, TypeError, ValueError):
        final_html = ""
    try:
        artifact = (
            parse_publish_readiness_payload(payload)
            if isinstance(payload, dict)
            else None
        )
        return plan_publish_readiness_refresh(
            report_id=report_id,
            readiness=artifact,
            final_html=final_html,
            configuration_hash=file_ctx.configuration_hash,
            policy_hash=file_ctx.policy_hash,
            producer_revision=file_ctx.producer_commit_sha,
            evaluated_at_utc=datetime.now(UTC),
        )
    except (AppError, OSError, TypeError, ValueError):
        return plan_publish_readiness_refresh(
            report_id=report_id,
            readiness=None,
            final_html=final_html,
            configuration_hash=file_ctx.configuration_hash,
            policy_hash=file_ctx.policy_hash,
            producer_revision=file_ctx.producer_commit_sha,
            evaluated_at_utc=datetime.now(UTC),
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
    existing = dependencies.existing_report_html(
        runtime.file,
        runtime.md5,
        settings,
        file_ctx,
    )
    runtime.report_checked_md5 = runtime.md5
    if isinstance(existing, RetainedReportPackage):
        runtime.retained_package = existing
        existing_html = existing.html_path
    else:
        existing_html = existing
    if not existing_html:
        return None
    readiness_plan = _existing_publish_readiness_refresh_plan(
        existing_html,
        report_id=(
            runtime.retained_package.report_id
            if runtime.retained_package is not None
            else runtime.file.file_id
        ),
        dependencies=dependencies,
        file_ctx=file_ctx,
    )
    if readiness_plan.previous_readiness_state != "ready":
        runtime.readiness_refresh_required = True
        runtime.readiness_refresh_plan = readiness_plan
        runtime.readiness_refresh_telemetry_path = str(
            Path(existing_html).with_suffix("")
            / "report_analysis"
            / "publish_readiness_refresh_plan.json"
        )
        logging.getLogger(logger_name).info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="report_html_cache_rejected",
                module=logger_name,
                fields={
                    "file_id": runtime.file.file_id,
                    "md5": runtime.md5,
                    "html_path": existing_html,
                    "matched_report_id": (
                        runtime.retained_package.report_id
                        if runtime.retained_package is not None
                        else runtime.file.file_id
                    ),
                    "readiness_status": readiness_plan.previous_readiness_state,
                    "refresh_reason": readiness_plan.reason,
                },
            )
        )
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
                "matched_report_id": (
                    runtime.retained_package.report_id
                    if runtime.retained_package is not None
                    else runtime.file.file_id
                ),
            },
        )
    )
    if runtime.retained_package is not None:
        record_report_source_reuse_telemetry(
            ReportSourceReuseTelemetryRecordRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                record=ReportSourceReuseTelemetryRecord(
                    schema_version="1.0",
                    incoming_file_id=runtime.file.file_id,
                    incoming_source_reference=f"drive:{runtime.file.file_id}",
                    canonical_source_identity=(
                        runtime.retained_package.canonical_source_identity
                    ),
                    source_content_hash=runtime.retained_package.source_content_hash,
                    matched_report_id=runtime.retained_package.report_id,
                    matched_source_metadata_hash=(
                        runtime.retained_package.source_metadata_hash
                    ),
                    decision="reuse",
                    decision_reason=runtime.retained_package.reason,
                    highest_reused_checkpoint="render_complete",
                    reused_stages=(
                        "acquisition",
                        "source_prepared",
                        "selection_complete",
                        "analysis_complete",
                        "render_complete",
                    ),
                    acquisition_actions_avoided=1,
                    browser_launches_avoided=1,
                    pdf_parse_avoided=1,
                    ocr_avoided=1,
                    extraction_avoided=1,
                    vector_work_avoided=1,
                ),
            ),
            file_ctx,
        )
    return _skip_result(
        index=index,
        file=runtime.file,
        display_name=runtime.display_name,
        md5=runtime.md5,
        html_path=existing_html,
        error="html_exists",
        publish_readiness_status="pass",
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
        run_budget=dependencies.run_budget,
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


def _record_permanent_source_failure(
    runtime: _IngestFileRuntime,
    *,
    settings: IngestSettings,
    dependencies: IngestFileDependencies,
    file_ctx: RunContext,
    error: AppError,
    logger_name: str,
) -> bool:
    if error.retryable or not error.code.startswith("pdf_"):
        return False
    integrity = (
        dependencies.check_pdf_integrity(
            PdfIntegrityCheckRequest(schema_version="1.0", path=runtime.cache_path),
            file_ctx,
        )
        if dependencies.check_pdf_integrity is not None
        else None
    )
    failure_code = str(getattr(integrity, "failure_code", "") or "").strip()
    if integrity is not None and not failure_code:
        return False
    md5 = (runtime.md5 or runtime.drive_md5 or "").strip()
    checksum = md5 or str(getattr(integrity, "sha256", "") or "").strip()
    if not checksum:
        return False
    if (
        dependencies.quarantine_enabled
        and dependencies.upsert_source_quarantine is not None
        and integrity is not None
    ):
        dependencies.upsert_source_quarantine(
            SourceQuarantineUpsertRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                record=SourceQuarantineRecord(
                    schema_version="1.0",
                    source_file_id=runtime.file.file_id,
                    content_checksum=checksum,
                    validator_version=str(integrity.validator_version),
                    status="active",
                    size_bytes=int(integrity.size_bytes),
                    failure_code=failure_code,
                    next_operator_action="revalidate_after_source_replacement",
                    first_observed_at_utc=str(integrity.validated_at_utc),
                    latest_observed_at_utc=str(integrity.validated_at_utc),
                    failed_validation_count=1,
                ),
            ),
            file_ctx,
        )
    last_error = f"{error.code}: {error.message}"
    dependencies.state_record(
        StateRecordRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            file_id=runtime.file.file_id,
            md5=checksum,
            openai_file_id="",
            vector_store_id=None,
            vector_store_status=None,
            indexed_at_utc=None,
            last_error=last_error,
            text_validation_status="fail",
            text_validation_reason=error.code,
            text_validation_pages=[],
            doc_map_summary=None,
            ocr_fallback_used=False,
            ocr_pdf_path=None,
        ),
        file_ctx,
    )
    logging.getLogger(logger_name).info(
        log_event(
            file_ctx,
            role="orchestrator",
            event="source_pdf_validation_failure_recorded",
            module=logger_name,
            fields={
                "file_id": runtime.file.file_id,
                "checksum": checksum,
                "error_code": failure_code or error.code,
                "quarantined": bool(integrity and dependencies.quarantine_enabled),
            },
        )
    )
    return True


def _validate_source_pdf_before_pipeline(
    runtime: _IngestFileRuntime,
    *,
    settings: IngestSettings,
    dependencies: IngestFileDependencies,
    file_ctx: RunContext,
    logger_name: str,
) -> None:
    """Stop deterministic structural failures before extraction, OCR, or model work."""
    if dependencies.check_pdf_integrity is None:
        return
    integrity = dependencies.check_pdf_integrity(
        PdfIntegrityCheckRequest(schema_version="1.0", path=runtime.cache_path),
        file_ctx,
    )
    failure_code = str(integrity.failure_code or "").strip()
    checksum = (runtime.drive_md5 or runtime.md5 or str(integrity.sha256 or "")).strip()
    if failure_code:
        raise AppError(
            code=f"pdf_integrity_{failure_code}",
            message="PDF failed deterministic structural integrity validation",
            retryable=bool(integrity.retryable),
            context={
                "file_id": runtime.file.file_id,
                "failure_code": failure_code,
                "validator_version": integrity.validator_version,
            },
        )
    if (
        dependencies.quarantine_enabled
        and dependencies.upsert_source_quarantine is not None
        and checksum
    ):
        dependencies.upsert_source_quarantine(
            SourceQuarantineUpsertRequest(
                schema_version="1.0",
                state_db=settings.state_db,
                record=SourceQuarantineRecord(
                    schema_version="1.0",
                    source_file_id=runtime.file.file_id,
                    content_checksum=checksum,
                    validator_version=integrity.validator_version,
                    status="cleared",
                    size_bytes=int(integrity.size_bytes),
                    failure_code="",
                    next_operator_action="",
                    first_observed_at_utc=integrity.validated_at_utc,
                    latest_observed_at_utc=integrity.validated_at_utc,
                    failed_validation_count=0,
                    cleared_at_utc=integrity.validated_at_utc,
                ),
            ),
            file_ctx,
        )
    logging.getLogger(logger_name).info(
        log_event(
            file_ctx,
            role="orchestrator",
            event="source_pdf_integrity_validated",
            module=logger_name,
            fields={
                "file_id": runtime.file.file_id,
                "validator_version": integrity.validator_version,
                "size_bytes": integrity.size_bytes,
                "quarantine_cleared": bool(
                    dependencies.quarantine_enabled and checksum
                ),
            },
        )
    )


def _matching_source_quarantine(
    runtime: _IngestFileRuntime,
    *,
    index: int,
    settings: IngestSettings,
    dependencies: IngestFileDependencies,
    file_ctx: RunContext,
    logger_name: str,
) -> FileProcessResult | None:
    checksum = (runtime.drive_md5 or "").strip()
    if (
        not dependencies.quarantine_enabled
        or not checksum
        or dependencies.get_source_quarantine is None
    ):
        return None
    response = dependencies.get_source_quarantine(
        SourceQuarantineGetRequest(
            schema_version="1.0",
            state_db=settings.state_db,
            source_file_id=runtime.file.file_id,
            content_checksum=checksum,
        ),
        file_ctx,
    )
    record = response.record
    if record is None or record.status != "active":
        return None
    logging.getLogger(logger_name).info(
        log_event(
            file_ctx,
            role="orchestrator",
            event="source_quarantine_skip",
            module=logger_name,
            fields={
                "file_id": runtime.file.file_id,
                "failure_code": record.failure_code,
                "validator_version": record.validator_version,
                "avoided_drive_download": True,
                "avoided_pdf_parse": True,
                "avoided_ocr": True,
                "avoided_model": True,
            },
        )
    )
    return _skip_result(
        index=index,
        file=runtime.file,
        display_name=runtime.display_name,
        md5=checksum,
        html_path=None,
        error=f"source_quarantined:{record.failure_code}",
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

        if runtime.retained_package is not None and runtime.readiness_refresh_required:
            canonical_file = replace(
                runtime.file, file_id=runtime.retained_package.report_id
            )
            outcome = dependencies.run_step_with_retry(
                "generate_report",
                file_ctx,
                lambda: _run_report_pipeline_latest_safe(
                    dependencies,
                    canonical_file,
                    runtime.cache_path,
                    settings,
                    runtime.md5,
                    file_ctx,
                    resume_from_stage="analysis_complete",
                    readiness_refresh_plan=runtime.readiness_refresh_plan,
                    refresh_telemetry_path=runtime.readiness_refresh_telemetry_path,
                ),
                0,
            )
            outcome = replace(
                outcome,
                file_id=runtime.file.file_id,
                name=runtime.display_name,
                md5=runtime.md5,
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
                    last_error=outcome.error or outcome.vector_store_last_error,
                    text_validation_status=outcome.text_validation_status,
                    text_validation_reason=outcome.text_validation_reason,
                    text_validation_pages=outcome.text_validation_pages,
                    doc_map_summary=outcome.doc_map_summary,
                    ocr_fallback_used=outcome.ocr_fallback_used,
                    ocr_pdf_path=outcome.ocr_pdf_path,
                ),
                file_ctx,
            )
            record_report_source_reuse_telemetry(
                ReportSourceReuseTelemetryRecordRequest(
                    schema_version="1.0",
                    db_path=settings.reports_db,
                    record=ReportSourceReuseTelemetryRecord(
                        schema_version="1.0",
                        incoming_file_id=runtime.file.file_id,
                        incoming_source_reference=f"drive:{runtime.file.file_id}",
                        canonical_source_identity=(
                            runtime.retained_package.canonical_source_identity
                        ),
                        source_content_hash=runtime.retained_package.source_content_hash,
                        matched_report_id=runtime.retained_package.report_id,
                        matched_source_metadata_hash=(
                            runtime.retained_package.source_metadata_hash
                        ),
                        decision="reuse",
                        decision_reason=runtime.retained_package.reason,
                        highest_reused_checkpoint="analysis_complete",
                        reused_stages=(
                            "acquisition",
                            "source_prepared",
                            "selection_complete",
                            "analysis_complete",
                        ),
                        regenerated_stages=("render_complete",),
                        acquisition_actions_avoided=1,
                        browser_launches_avoided=1,
                        pdf_parse_avoided=1,
                        ocr_avoided=1,
                        extraction_avoided=1,
                        vector_work_avoided=1,
                    ),
                ),
                file_ctx,
            )
            logger.info(
                log_event(
                    file_ctx,
                    role="orchestrator",
                    event="canonical_source_package_reused",
                    module=logger_name,
                    fields={
                        "incoming_file_id": runtime.file.file_id,
                        "canonical_source_identity": (
                            runtime.retained_package.canonical_source_identity
                        ),
                        "matched_report_id": runtime.retained_package.report_id,
                        "highest_reused_checkpoint": "analysis_complete",
                        "reused_stages": [
                            "acquisition",
                            "source_prepared",
                            "selection_complete",
                            "analysis_complete",
                        ],
                        "regenerated_stages": ["render_complete"],
                        "decision_reason": runtime.retained_package.reason,
                        "model_calls_avoided_status": "unavailable",
                        "tokens_avoided_status": "unavailable",
                        "estimated_cost_avoided_status": "unavailable",
                        "acquisition_avoided": True,
                        "browser_avoided": True,
                        "pdf_ocr_avoided": True,
                    },
                )
            )
            return _file_result(
                index=index,
                outcome=outcome,
                processed=1,
                had_error=outcome.status == "error",
            )

        quarantined = _matching_source_quarantine(
            runtime,
            index=index,
            settings=settings,
            dependencies=dependencies,
            file_ctx=file_ctx,
            logger_name=logger_name,
        )
        if quarantined is not None:
            return quarantined

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
            and not dependencies.bypass_existing_report_html
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
        _validate_source_pdf_before_pipeline(
            runtime,
            settings=settings,
            dependencies=dependencies,
            file_ctx=file_ctx,
            logger_name=logger_name,
        )
        record_validation_manifest_stage(
            settings=settings,
            ctx=file_ctx,
            stage="acquisition",
            source_identity_id=runtime.md5 or runtime.file.file_id,
            input_artifact_ids=(runtime.file.file_id,),
            output_artifact_ids=(runtime.cache_path,),
            idempotency_state="reused" if cache_hit else "new",
        )
        record_validation_manifest_stage(
            settings=settings,
            ctx=file_ctx,
            stage="source_preparation",
            source_identity_id=runtime.md5 or runtime.file.file_id,
            input_artifact_ids=(runtime.cache_path,),
            output_artifact_ids=(runtime.md5 or runtime.file.file_id,),
        )
        record_validation_manifest_stage(
            settings=settings,
            ctx=file_ctx,
            stage="source_validation",
            source_identity_id=runtime.md5 or runtime.file.file_id,
            input_artifact_ids=(runtime.cache_path,),
            output_artifact_ids=(runtime.md5 or runtime.file.file_id,),
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
                resume_from_stage=(
                    "analysis_complete" if runtime.readiness_refresh_required else None
                ),
                readiness_refresh_plan=runtime.readiness_refresh_plan,
                refresh_telemetry_path=runtime.readiness_refresh_telemetry_path,
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
            _record_ingest_file_failure(
                runtime=runtime,
                settings=settings,
                error=AppError(
                    code="ingest_file_report_pipeline_failed",
                    message=outcome.error
                    or "The report pipeline returned an error outcome",
                    retryable=False,
                ),
                ctx=file_ctx,
            )
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
        _record_ingest_file_failure(
            runtime=runtime,
            settings=settings,
            error=exc,
            ctx=file_ctx,
        )
        recorded_source_failure = False
        if isinstance(exc, AppError):
            recorded_source_failure = _record_permanent_source_failure(
                runtime,
                settings=settings,
                dependencies=dependencies,
                file_ctx=file_ctx,
                error=exc,
                logger_name=logger_name,
            )
        error_md5 = runtime.md5 or runtime.drive_md5 or None
        if error_md5 and not recorded_source_failure:
            if isinstance(exc, AppError):
                last_error = f"{exc.code}: {exc.message}"
            else:
                last_error = f"{type(exc).__name__}: {exc}"
            dependencies.state_record(
                StateRecordRequest(
                    schema_version="1.0",
                    state_db=settings.state_db,
                    file_id=runtime.file.file_id,
                    md5=error_md5,
                    last_error=last_error,
                ),
                file_ctx,
            )
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
                md5=error_md5,
                html_path=None,
                status="error",
                error=str(exc),
            ),
            processed=0,
            had_error=True,
        )
