from __future__ import annotations

import json
import logging
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from dataclasses import asdict, dataclass, field, replace
from datetime import datetime, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional

from src.contracts.drive import (
    DriveDownloadToPathRequest,
    DriveFile,
    DriveFileMetadataRequest,
    DriveListRequest,
)
from src.contracts.file_cache import (
    FileCacheMd5SidecarResolveRequest,
    FileCacheMd5SidecarWriteRequest,
)
from src.contracts.files import (
    DeleteFileRequest,
    FileExistsRequest,
    FileStatRequest,
    ReadTextRequest,
    WriteBytesRequest,
)
from src.contracts.ingest import IngestOutcome, IngestSettings
from src.contracts.llm_usage import LLMUsageProjectionStatusRequest
from src.contracts.pdf_text import PdfTextExtractRequest
from src.contracts.pdf_utils import (
    PdfEofCheckRequest,
    PdfIntegrityCheckRequest,
)
from src.contracts.report_cards import ReportCardManifest
from src.contracts.report_store import (
    ReportMetadataGetRequest,
    ReportSourceIdentityGetRequest,
    SourceIdentityObservationRecordRequest,
)
from src.contracts.run_budget import RunBudget
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import RunId, ValidationRunId
from src.contracts.state import (
    SourceQuarantineGetRequest,
    StateBatchCheckItem,
    StateBatchCheckRequest,
    StateCheckRequest,
    StateGetRequest,
    StateGetResponse,
    StateIngestCursorGetRequest,
    StateIngestCursorSetRequest,
)
from src.contracts.validation_reliability import (
    ValidationReliabilityBuildRequest,
    ValidationReliabilityWriteRequest,
)
from src.contracts.validation_run_manifest import (
    ValidationRunManifestAuditRequest,
    ValidationRunManifestAttemptResolveRequest,
    ValidationRunManifestCreateRequest,
    ValidationRunManifestRecordRequest,
    ValidationRunManifestStageRecord,
)
from src.generators.report_generation_shared import report_slug
from src.orchestrators._ingest_orchestrator.db_preflight import (
    verify_ingest_db_access,
)
from src.orchestrators._ingest_orchestrator.lock_lifecycle import (
    acquire_ingest_lock,
    finalize_ingest_run,
)
from src.orchestrators.admission_preflight_orchestrator import (
    AdmissionPreflightDependencies,
    AdmissionPreflightRequest,
    admission_configuration_hash,
    admission_configuration_snapshot,
    admission_decision_payload,
    admission_policy_hash,
    pipeline_preflight_decision_hash,
    run_admission_preflight,
)
from src.orchestrators.ingest_file_orchestrator import (
    FileProcessResult as _FileProcessResult,
)
from src.orchestrators.ingest_file_orchestrator import (
    IngestFileDependencies,
    run_ingest_file,
)
from src.orchestrators.pipeline_preflight_orchestrator import (
    preflight_report_pipeline,
)
from src.orchestrators.remediation_orchestrator import (
    record_workflow_failure,
    remediation_input_checksum,
)
from src.orchestrators.report_pipeline_orchestrator import (
    run_report_pipeline as run_report_pipeline_orchestrator,
)
from src.orchestrators.retry_orchestrator import run_step_with_default_policy
from src.orchestrators.vector_store_retention_orchestrator import (
    run_vector_store_retention_cleanup,
)
from src.services.drive_service import (
    download_pdf_to_path,
    get_file_metadata,
    list_pdfs,
)
from src.services.file_cache_service import (
    resolve_md5_sidecar,
    write_md5_sidecar,
)
from src.services.file_service import (
    delete_file,
    file_exists,
    file_stat,
    read_text,
    write_bytes,
)
from src.services.llm_usage_ledger_service import (
    evaluate_budget_request,
    finalize_usage_projection,
)
from src.services.pdf_service import (
    check_pdf_eof,
    check_pdf_integrity,
    extract_pdf_text,
)
from src.services.report_store_service import (
    audit_validation_run_manifest,
    create_validation_run_manifest,
    get_report_source_identity,
    record_source_identity_observation,
    record_validation_run_manifest_stage,
    resolve_validation_run_manifest_attempt,
)
from src.services.report_store_service import (
    get_metadata as get_report_metadata,
)
from src.services.state_service import already_processed as state_already_processed
from src.services.state_service import (
    already_processed_batch as state_already_processed_batch,
)
from src.services.state_service import get as state_get
from src.services.state_service import (
    get_ingest_cursor,
    get_source_quarantine,
    set_ingest_cursor,
    upsert_source_quarantine,
)
from src.services.state_service import record as state_record
from src.services.validation_reliability_service import (
    build_validation_reliability_artifact,
    validation_reliability_artifact_path,
    write_validation_reliability_artifact,
)
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.path_utils import safe_pdf_name

logger = logging.getLogger("market_lense.ingest_orchestrator")
EOF_RETRY_LIMIT = 1
STATE_PREFILTER_BATCH_SIZE = 200
DOC_MAP_EMPTY_ERROR_PREFIX = "doc_map_empty:"
COHORT_MANIFEST_SCHEMA_VERSION = "1.1"
_SUPPORTED_COHORT_MANIFEST_SCHEMA_VERSIONS = frozenset(
    {"1.0", COHORT_MANIFEST_SCHEMA_VERSION}
)


@dataclass(frozen=True)
class IngestBatchDependencies:
    list_pdfs: Callable[[DriveListRequest, RunContext], Iterable[DriveFile]]
    batch_should_skip: Callable[
        [list[DriveFile], str, RunContext], dict[tuple[str, str], bool]
    ]
    process_file: Callable[
        [DriveFile, int, IngestSettings, RunContext, bool], _FileProcessResult
    ]
    thread_pool_executor_factory: Callable[[int], Any]
    file_exists: Callable[[FileExistsRequest, RunContext], Any] = field(
        default=file_exists
    )
    read_text: Callable[[ReadTextRequest, RunContext], Any] = field(default=read_text)
    write_bytes: Callable[[WriteBytesRequest, RunContext], Any] = field(
        default=write_bytes
    )
    get_report_metadata: Callable[[ReportMetadataGetRequest, RunContext], Any] = field(
        default=get_report_metadata
    )
    vector_store_retention_cleanup: Callable[[IngestSettings, RunContext], Any] = field(
        default=run_vector_store_retention_cleanup
    )
    check_pdf_integrity: Callable[[PdfIntegrityCheckRequest, RunContext], Any] = field(
        default=check_pdf_integrity
    )
    extract_pdf_text: Callable[[PdfTextExtractRequest, RunContext], Any] = field(
        default=extract_pdf_text
    )
    get_source_quarantine: Callable[[SourceQuarantineGetRequest, RunContext], Any] = (
        field(default=get_source_quarantine)
    )
    evaluate_budget_request: Callable[[Any, RunContext], Any] = field(
        default=evaluate_budget_request
    )
    get_source_identity: Callable[[ReportSourceIdentityGetRequest, RunContext], Any] = (
        field(default=get_report_source_identity)
    )
    record_source_identity_observation: Callable[
        [SourceIdentityObservationRecordRequest, RunContext], Any
    ] = field(default=record_source_identity_observation)

    @classmethod
    def default(cls) -> "IngestBatchDependencies":
        return cls(
            list_pdfs=list_pdfs,
            batch_should_skip=_batch_should_skip,
            process_file=_process_file,
            thread_pool_executor_factory=ThreadPoolExecutor,
        )


def _should_skip(
    file: DriveFile, md5: Optional[str], state_db: str, ctx: RunContext
) -> bool:
    if not md5:
        return False
    req = StateCheckRequest(
        schema_version="1.0",
        state_db=state_db,
        file_id=file.file_id,
        md5=md5,
    )
    if not state_already_processed(req, ctx):
        return False
    return _processed_state_should_skip(file.file_id, md5, state_db, ctx)


def _processed_state_should_skip(
    file_id: str,
    md5: str,
    state_db: str,
    ctx: RunContext,
) -> bool:
    record = state_get(
        StateGetRequest(schema_version="1.0", state_db=state_db, file_id=file_id),
        ctx,
    )
    if record is None or record.md5 != md5:
        return False
    return _processed_record_should_skip(record, ctx)


def _processed_record_should_skip(
    record: StateGetResponse,
    ctx: RunContext,
) -> bool:
    file_id = record.file_id
    md5 = record.md5
    last_error = str(record.last_error or "").strip()
    text_validation_status = str(record.text_validation_status or "").strip().lower()
    if last_error.startswith("report_pipeline_checkpoint_lineage_not_reusable:"):
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="processed_state_checkpoint_repair_selected",
                module=logger.name,
                fields={
                    "file_id": file_id,
                    "md5": md5,
                    "last_error": last_error,
                },
            )
        )
        return False
    if last_error == "publish_readiness_failed" or last_error.startswith(
        "cover_fingerprint_invalid:"
    ):
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="processed_state_report_generation_repair_selected",
                module=logger.name,
                fields={
                    "file_id": file_id,
                    "md5": md5,
                    "last_error": last_error,
                },
            )
        )
        return False
    if not last_error and text_validation_status not in {"pass", "fail"}:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="processed_state_progress_retry_selected",
                module=logger.name,
                fields={
                    "file_id": file_id,
                    "md5": md5,
                    "vector_store_status": record.vector_store_status or "",
                },
            )
        )
        return False
    if (
        last_error.startswith(DOC_MAP_EMPTY_ERROR_PREFIX)
        and text_validation_status == "pass"
    ):
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="processed_state_doc_map_retry_selected",
                module=logger.name,
                fields={
                    "file_id": file_id,
                    "md5": md5,
                    "last_error": last_error,
                    "text_validation_status": text_validation_status,
                },
            )
        )
        return False
    return True


def _batch_should_skip(
    files: list[DriveFile],
    state_db: str,
    ctx: RunContext,
) -> dict[tuple[str, str], bool]:
    items = []
    for file in files:
        md5 = file.md5_checksum.strip() if file.md5_checksum else ""
        if not md5:
            continue
        items.append(
            StateBatchCheckItem(schema_version="1.0", file_id=file.file_id, md5=md5)
        )
    if not items:
        return {}
    response = state_already_processed_batch(
        StateBatchCheckRequest(
            schema_version="1.0",
            state_db=state_db,
            items=items,
        ),
        ctx,
    )
    processed = {(item.file_id, item.md5) for item in response.processed_items}
    records_by_key = {
        (record.file_id, record.md5): record
        for record in getattr(response, "processed_records", [])
    }
    lookup: dict[tuple[str, str], bool] = {}
    retryable_matches = 0
    for item in items:
        key = (item.file_id, item.md5)
        if key not in processed:
            lookup[key] = False
            continue
        record = records_by_key.get(key)
        should_skip = (
            _processed_record_should_skip(record, ctx)
            if record is not None
            else _processed_state_should_skip(item.file_id, item.md5, state_db, ctx)
        )
        if not should_skip:
            retryable_matches += 1
        lookup[key] = should_skip
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="drive_list_state_batch_checked",
            module=logger.name,
            fields={
                "checked": len(items),
                "matched": len(processed),
                "skipped": sum(1 for should_skip in lookup.values() if should_skip),
                "retryable_matches": retryable_matches,
            },
        )
    )
    return lookup


def _cache_pdf_path(settings: IngestSettings, file: DriveFile) -> str:
    cache_name = safe_pdf_name(file.file_id)
    return str(Path(settings.cache_dir) / cache_name)


def _ensure_file_name(
    file: DriveFile,
    settings: IngestSettings,
    ctx: RunContext,
    *,
    get_file_metadata_fn: Callable[[DriveFileMetadataRequest, RunContext], Any] = (
        get_file_metadata
    ),
) -> DriveFile:
    if file.name:
        return file
    try:
        meta = get_file_metadata_fn(
            DriveFileMetadataRequest(
                schema_version="1.0",
                file_id=file.file_id,
                service_account_path=settings.google_sa_path,
                auth_mode=settings.drive_auth_mode,
                oauth_client_path=settings.google_oauth_client_path,
                oauth_token_path=settings.google_oauth_token_path,
                run_budget=_ingest_run_budget(settings, ctx),
            ),
            ctx,
        ).file
        return DriveFile(
            schema_version="1.0",
            file_id=file.file_id,
            name=meta.name or file.file_id,
            modified_time=meta.modified_time or file.modified_time,
            md5_checksum=file.md5_checksum or meta.md5_checksum,
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="drive_file_metadata_failed",
                module=logger.name,
                fields={"file_id": file.file_id, "error": exc.message},
            )
        )
        return DriveFile(
            schema_version="1.0",
            file_id=file.file_id,
            name=file.file_id,
            modified_time=file.modified_time,
            md5_checksum=file.md5_checksum,
        )


def _existing_report_html(
    file: DriveFile,
    md5: str,
    settings: IngestSettings,
    ctx: RunContext,
) -> Optional[str]:
    if not md5:
        return None
    try:
        metadata = get_report_metadata(
            ReportMetadataGetRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                file_id=file.file_id,
            ),
            ctx,
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_metadata_lookup_failed",
                module=logger.name,
                fields={"file_id": file.file_id, "error": str(exc)},
            )
        )
        return None
    if not metadata or not metadata.md5 or metadata.md5 != md5:
        return None
    html_path = (metadata.html_path or "").strip()
    if not html_path:
        return None
    html_stat = file_stat(FileStatRequest(schema_version="1.0", path=html_path), ctx)
    if not html_stat.exists:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_html_missing",
                module=logger.name,
                fields={"file_id": file.file_id, "md5": md5, "html_path": html_path},
            )
        )
        return None
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_html_cache_hit",
            module=logger.name,
            fields={"file_id": file.file_id, "md5": md5, "html_path": html_path},
        )
    )
    return html_path


def _run_step_with_retry(step_name: str, ctx: RunContext, func, retries: int = 2):
    return run_step_with_default_policy(
        step_name=step_name,
        operation=func,
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        retries=retries,
        sleep_fn=time.sleep,
    )


def _report_pipeline_resume_options(
    *,
    force_report_cards: bool,
    has_existing_report_html: bool,
    auto_resume_from_latest_safe: bool,
) -> tuple[str | None, bool]:
    if force_report_cards and has_existing_report_html:
        return "analysis_complete", False
    return None, auto_resume_from_latest_safe


def _process_file(
    file: DriveFile,
    index: int,
    settings: IngestSettings,
    root_ctx: RunContext,
    force_report_cards: bool,
) -> _FileProcessResult:
    file_ctx = replace(
        root_ctx,
        report_id=file.file_id,
        source_identity_id=(file.md5_checksum or file.file_id),
        publisher_id=(root_ctx.publisher_id or "unattributed"),
        workflow="report_generation",
        stage="report_pipeline",
        artifact_family="report",
    )

    def _run_pipeline(
        current_file: DriveFile,
        local_pdf_path: str,
        current_settings: IngestSettings,
        current_md5: str | None,
        current_ctx: RunContext,
        **kwargs: object,
    ) -> IngestOutcome:
        has_existing_report_html = bool(
            current_md5
            and _existing_report_html(
                current_file,
                current_md5,
                current_settings,
                current_ctx,
            )
        )
        resume_from_stage, auto_resume = _report_pipeline_resume_options(
            force_report_cards=force_report_cards,
            has_existing_report_html=has_existing_report_html,
            auto_resume_from_latest_safe=bool(
                kwargs.get("auto_resume_from_latest_safe", False)
            ),
        )
        return run_report_pipeline_orchestrator(
            current_file,
            local_pdf_path,
            current_settings,
            current_md5,
            current_ctx,
            retries=2,
            resume_from_stage=resume_from_stage,
            auto_resume_from_latest_safe=auto_resume,
        )

    dependencies = IngestFileDependencies(
        should_skip=_should_skip,
        cache_pdf_path=_cache_pdf_path,
        resolve_md5_sidecar=resolve_md5_sidecar,
        ensure_file_name=_ensure_file_name,
        write_md5_sidecar=write_md5_sidecar,
        existing_report_html=_existing_report_html,
        run_step_with_retry=_run_step_with_retry,
        file_stat=file_stat,
        download_pdf_to_path=download_pdf_to_path,
        check_pdf_eof=check_pdf_eof,
        delete_file=delete_file,
        run_report_pipeline=_run_pipeline,
        state_record=state_record,
        eof_retry_limit=EOF_RETRY_LIMIT,
        read_text=read_text,
        bypass_existing_report_html=force_report_cards,
        check_pdf_integrity=check_pdf_integrity,
        get_source_quarantine=get_source_quarantine,
        upsert_source_quarantine=upsert_source_quarantine,
        quarantine_enabled=settings.source_quarantine_enabled,
        run_budget=_ingest_run_budget(settings, file_ctx),
    )
    return run_ingest_file(
        file=file,
        index=index,
        settings=settings,
        root_ctx=file_ctx,
        dependencies=dependencies,
        logger_name=logger.name,
    )


def _resolve_modified_after(
    settings: IngestSettings,
    *,
    limit: Optional[int],
    force_report_cards: bool,
    rescan: bool,
    root_ctx: RunContext,
) -> Optional[str]:
    del limit
    if rescan:
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_modified_after_ignored",
                module=logger.name,
                fields={"reason": "rescan"},
            )
        )
        return None
    if force_report_cards:
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_modified_after_ignored",
                module=logger.name,
                fields={"reason": "force_report_cards"},
            )
        )
        return None
    cursor_resp = get_ingest_cursor(
        StateIngestCursorGetRequest(
            schema_version="1.0",
            state_db=settings.state_db,
        ),
        root_ctx,
    )
    modified_after = cursor_resp.last_successful_ingest_utc
    if modified_after:
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_modified_after_loaded",
                module=logger.name,
                fields={"modified_after": modified_after},
            )
        )
    return modified_after


def _build_drive_list_request(
    settings: IngestSettings,
    *,
    folder_id: Optional[str],
    limit: Optional[int],
    modified_after: Optional[str],
    ctx: RunContext,
) -> DriveListRequest:
    max_n = limit if limit is not None else settings.batch_limit
    return DriveListRequest(
        schema_version="1.0",
        folder_id=folder_id or settings.gdrive_folder_id,
        service_account_path=settings.google_sa_path,
        auth_mode=settings.drive_auth_mode,
        oauth_client_path=settings.google_oauth_client_path,
        oauth_token_path=settings.google_oauth_token_path,
        page_size=min(max_n, 1000) if limit is not None else None,
        order_by="modifiedTime desc" if limit is not None else None,
        modified_after=modified_after,
        list_mode=settings.drive_list_mode,
        supports_all_drives=settings.drive_supports_all_drives,
        include_items_from_all_drives=settings.drive_include_items_from_all_drives,
        drive_id=settings.drive_id,
        run_budget=_ingest_run_budget(settings, ctx),
    )


def _ingest_run_budget(settings: IngestSettings, ctx: RunContext) -> RunBudget:
    """Build the one isolated budget scope used by every Drive action in a run."""
    return RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name="",
        usage_db_path=settings.usage_db_path,
        max_spend_usd=settings.run_budget_max_spend_usd,
        max_pdfs=settings.run_budget_max_pdfs,
        max_retries=settings.run_budget_max_retries,
        max_runtime_seconds=settings.run_budget_max_runtime_seconds,
        limit_decision=settings.run_budget_limit_decision,
        enabled_effect_kinds=settings.run_budget_enabled_effect_kinds,
    )


def _materialize_files_to_process(
    list_req: DriveListRequest,
    *,
    settings: IngestSettings,
    max_n: int,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
    force_report_cards: bool,
    excluded_file_ids: set[str] | None = None,
) -> list[DriveFile]:
    files_to_process: list[DriveFile] = []
    pending_md5_files: list[DriveFile] = []
    excluded = excluded_file_ids or set()

    if max_n <= 0:
        return files_to_process

    def _flush_pending_md5_files() -> None:
        nonlocal pending_md5_files
        if not pending_md5_files:
            return
        lookup = deps.batch_should_skip(pending_md5_files, settings.state_db, root_ctx)
        for pending in pending_md5_files:
            drive_md5 = pending.md5_checksum.strip() if pending.md5_checksum else ""
            should_skip = bool(
                drive_md5 and lookup.get((pending.file_id, drive_md5), False)
            )
            if should_skip and force_report_cards:
                should_skip = _report_card_backfill_should_skip(
                    pending,
                    settings=settings,
                    deps=deps,
                    root_ctx=root_ctx,
                )
            if should_skip:
                logger.info(
                    log_event(
                        root_ctx,
                        role="orchestrator",
                        event="drive_list_skip_processed",
                        module=logger.name,
                        fields={"file_id": pending.file_id, "md5": drive_md5},
                    )
                )
                continue
            files_to_process.append(pending)
            if len(files_to_process) >= max_n:
                break
        pending_md5_files = []

    for file in deps.list_pdfs(list_req, root_ctx):
        if file.file_id in excluded:
            logger.info(
                log_event(
                    root_ctx,
                    role="orchestrator",
                    event="drive_list_skip_attempted",
                    module=logger.name,
                    fields={"file_id": file.file_id},
                )
            )
            continue
        drive_md5 = file.md5_checksum.strip() if file.md5_checksum else None
        if drive_md5:
            pending_md5_files.append(file)
            if len(pending_md5_files) >= STATE_PREFILTER_BATCH_SIZE:
                _flush_pending_md5_files()
                if len(files_to_process) >= max_n:
                    break
            continue
        files_to_process.append(file)
        if len(files_to_process) >= max_n:
            break

    if len(files_to_process) < max_n:
        _flush_pending_md5_files()
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="drive_list_materialized",
            module=logger.name,
            fields={
                "count": len(files_to_process),
                "limit": max_n,
                "excluded_count": len(excluded),
            },
        )
    )
    return files_to_process


def _cohort_admission_preflight(
    files: list[DriveFile],
    *,
    settings: IngestSettings,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
    admitted_source_identities: set[str] | None = None,
    admitted_title_keys: set[str] | None = None,
    admission_decisions: list[dict[str, Any]] | None = None,
    runtime_preflight_passed: bool = True,
    runtime_preflight_hash: str = "",
) -> list[DriveFile]:
    """Admit deterministic, locally verifiable sources before freezing a cohort.

    Acquisition may populate the local cache before this check, but no model,
    vector-store, or report-generation work occurs until the admitted members
    are persisted in the immutable manifest.
    """
    admitted: list[DriveFile] = []
    known_source_identities = (
        admitted_source_identities if admitted_source_identities is not None else set()
    )
    known_title_keys = admitted_title_keys if admitted_title_keys is not None else set()
    known_source_lookup = {identity: identity for identity in known_source_identities}
    known_title_lookup = {title_key: title_key for title_key in known_title_keys}
    admission_dependencies = AdmissionPreflightDependencies(
        check_pdf_integrity=deps.check_pdf_integrity,
        extract_pdf_text=deps.extract_pdf_text,
        get_source_quarantine=deps.get_source_quarantine,
        evaluate_budget_request=deps.evaluate_budget_request,
        get_source_identity=deps.get_source_identity,
        record_source_identity_observation=deps.record_source_identity_observation,
    )
    for file in files:
        file_ctx = child_context(root_ctx, task_id=f"admission:{file.file_id}")
        result = run_admission_preflight(
            AdmissionPreflightRequest(
                file=file,
                source_artifact_path=_cache_pdf_path(settings, file),
                settings=settings,
                runtime_preflight_passed=runtime_preflight_passed,
                runtime_preflight_hash=runtime_preflight_hash,
                configuration_hash=admission_configuration_hash(settings),
                policy_hash=admission_policy_hash(settings),
                known_source_identities=known_source_lookup,
                known_title_keys=known_title_lookup,
            ),
            file_ctx,
            dependencies=admission_dependencies,
        )
        decision = result.decision
        if admission_decisions is not None:
            row = admission_decision_payload(decision)
            row["title_key"] = _admission_title_key(file.name)
            row["runtime_dependency_status"] = (
                "validated_pre_freeze"
                if runtime_preflight_passed
                else "blocked_pre_freeze"
            )
            admission_decisions.append(row)
        logger.info(
            log_event(
                file_ctx,
                role="orchestrator",
                event="ingest_cohort_admission_preflight_complete",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "source_identity_id": decision.source_identity_id,
                    "outcome": decision.outcome,
                    "admission_preflight_version": decision.preflight_version,
                    "admission_decision_hash": decision.decision_hash,
                },
            )
        )
        if result.admitted:
            admitted.append(file)
            known_source_identities.add(decision.source_identity_id)
            known_source_lookup[decision.source_identity_id] = (
                decision.source_identity_id
            )
            title_key = _admission_title_key(file.name)
            if title_key:
                known_title_keys.add(title_key)
                known_title_lookup[title_key] = title_key
    return admitted


def _admission_title_key(name: str | None) -> str:
    """Return a deterministic title fallback used only for duplicate admission."""
    stem = Path(str(name or "")).stem.casefold()
    return "".join(character for character in stem if character.isalnum())


def _select_admitted_cohort(
    *,
    cohort_size: int,
    list_req: DriveListRequest,
    settings: IngestSettings,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
    force_report_cards: bool,
    runtime_preflight_passed: bool,
    runtime_preflight_hash: str,
) -> tuple[list[DriveFile], list[dict[str, Any]]]:
    """Select the first ordered candidates that pass admission before freezing.

    A source rejected during admission is never a cohort member.  This differs
    from a post-manifest failure: the latter is recorded against the fixed
    member and can never trigger a replacement.
    """
    admitted: list[DriveFile] = []
    attempted_file_ids: set[str] = set()
    admitted_source_identities: set[str] = set()
    admitted_title_keys: set[str] = set()
    admission_decisions: list[dict[str, Any]] = []
    admission_batches = 0
    while len(admitted) < cohort_size:
        remaining = cohort_size - len(admitted)
        candidates = _materialize_files_to_process(
            list_req,
            settings=settings,
            max_n=remaining,
            deps=deps,
            root_ctx=root_ctx,
            force_report_cards=force_report_cards,
            excluded_file_ids=attempted_file_ids,
        )
        if not candidates:
            _persist_admission_funnel(
                admission_decisions,
                settings=settings,
                deps=deps,
                root_ctx=root_ctx,
            )
            raise AppError(
                code="ingest_cohort_insufficient_eligible_reports",
                message="Insufficient eligible reports to freeze the requested cohort",
                retryable=False,
                context={
                    "requested": cohort_size,
                    "admitted": len(admitted),
                    "admission_candidates_examined": len(attempted_file_ids),
                },
            )
        attempted_file_ids.update(file.file_id for file in candidates)
        candidates = _prefetch_drive_cache_stage(
            candidates,
            settings=settings,
            deps=deps,
            root_ctx=root_ctx,
        )
        newly_admitted = _cohort_admission_preflight(
            candidates,
            settings=settings,
            deps=deps,
            root_ctx=root_ctx,
            admitted_source_identities=admitted_source_identities,
            admitted_title_keys=admitted_title_keys,
            admission_decisions=admission_decisions,
            runtime_preflight_passed=runtime_preflight_passed,
            runtime_preflight_hash=runtime_preflight_hash,
        )
        admitted.extend(newly_admitted[:remaining])
        admission_batches += 1
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_cohort_admission_selection_batch_complete",
                module=logger.name,
                fields={
                    "batch_number": admission_batches,
                    "candidate_count": len(candidates),
                    "admitted_count": len(newly_admitted),
                    "cohort_admitted_count": len(admitted),
                    "cohort_target": cohort_size,
                    "rejected_count": len(candidates) - len(newly_admitted),
                },
            )
        )
    _persist_admission_funnel(
        admission_decisions,
        settings=settings,
        deps=deps,
        root_ctx=root_ctx,
    )
    return admitted, admission_decisions


def _load_frozen_cohort(
    *,
    cohort_manifest: str,
    expected_size: int | None,
    expected_configuration_hash: str = "",
    expected_policy_hash: str = "",
    expected_producer_build_identity: str = "",
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
) -> tuple[int, list[DriveFile]]:
    """Read and validate a persisted cohort without consulting the Drive listing."""
    try:
        payload = json.loads(
            deps.read_text(
                ReadTextRequest(schema_version="1.0", path=cohort_manifest),
                root_ctx,
            ).content
        )
        members = payload["members"]
        manifest_size = int(payload["cohort_size"])
        manifest_schema_version = str(payload.get("schema_version") or "")
        if (
            manifest_schema_version not in _SUPPORTED_COHORT_MANIFEST_SCHEMA_VERSIONS
            or manifest_size < 1
            or expected_size not in {None, manifest_size}
            or not isinstance(members, list)
            or len(members) != manifest_size
        ):
            raise ValueError("manifest schema or cohort size is invalid")
        files = [
            DriveFile(
                schema_version="1.0",
                file_id=str(member["file_id"]),
                name=member.get("name"),
                modified_time=member.get("modified_time"),
                md5_checksum=member.get("md5_checksum"),
                mime_type=member.get("mime_type"),
            )
            for member in members
        ]
        if len({file.file_id for file in files}) != manifest_size:
            raise ValueError("manifest contains duplicate file IDs")
        computed_cohort_id = _cohort_id(files)
        if str(payload.get("cohort_id") or "") != computed_cohort_id:
            raise ValueError("manifest cohort identity does not match its members")
        if manifest_schema_version == COHORT_MANIFEST_SCHEMA_VERSION:
            for member, file in zip(members, files, strict=True):
                if not isinstance(member, dict):
                    raise ValueError("manifest member must be an object")
                if str(member.get("report_id") or "") != file.file_id:
                    raise ValueError("manifest member report identity is invalid")
                if str(member.get("source_identity_id") or "") != (
                    file.md5_checksum or file.file_id
                ):
                    raise ValueError("manifest member source identity is invalid")
                if not str(member.get("publisher_id") or "").strip():
                    raise ValueError("manifest member publisher identity is invalid")
                if str(member.get("selection_reason") or "") != (
                    "deterministic_admission_preflight"
                ):
                    raise ValueError("manifest member selection reason is invalid")
    except (KeyError, TypeError, ValueError, json.JSONDecodeError) as exc:
        raise AppError(
            code="ingest_cohort_manifest_invalid",
            message="Cohort manifest is not a valid immutable ingest cohort",
            cause=exc,
            retryable=False,
        ) from exc
    expected_provenance = {
        "configuration_hash": expected_configuration_hash,
        "policy_hash": expected_policy_hash,
        "producer_build_identity": expected_producer_build_identity,
    }
    observed_provenance = {
        "configuration_hash": str(payload.get("configuration_hash") or ""),
        "policy_hash": str(payload.get("policy_hash") or ""),
        # Cohorts before provenance-bound validation IDs were written from a
        # workspace checkout and therefore have no explicit build identity.
        "producer_build_identity": str(
            payload.get("producer_build_identity") or "workspace"
        ),
    }
    if any(expected_provenance.values()) and observed_provenance != expected_provenance:
        raise AppError(
            code="ingest_cohort_provenance_stale",
            message=(
                "Cohort manifest provenance differs from current admission "
                "configuration, policy, or producer identity"
            ),
            retryable=False,
        )
    if manifest_schema_version == COHORT_MANIFEST_SCHEMA_VERSION:
        expected_validation_run_id = _validation_run_id_for_cohort(
            cohort_id=computed_cohort_id,
            configuration_hash=observed_provenance["configuration_hash"],
            policy_hash=observed_provenance["policy_hash"],
            producer_build_identity=observed_provenance["producer_build_identity"],
        )
        if str(payload.get("validation_run_id") or "") != str(
            expected_validation_run_id
        ):
            raise AppError(
                code="ingest_cohort_manifest_invalid",
                message="Cohort manifest validation identity is inconsistent",
                retryable=False,
            )
    return manifest_size, files


def recover_frozen_cohort_provenance(
    *,
    source_manifest: str,
    recovery_manifest: str,
    recovery_reason: str,
    allow_producer_transition: bool = False,
    allow_policy_transition: bool = False,
    settings: IngestSettings,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
) -> list[DriveFile]:
    """Create a linked validation manifest for an immutable-cohort recovery.

    The source remains immutable and every member is preserved exactly.
    Producer and policy transitions each require explicit operator opt-in.
    """
    if not source_manifest or source_manifest == recovery_manifest:
        raise AppError(
            code="ingest_cohort_provenance_recovery_target_invalid",
            message="Provenance recovery requires a distinct target manifest",
            retryable=False,
        )
    if not recovery_reason.strip():
        raise AppError(
            code="ingest_cohort_provenance_recovery_reason_required",
            message="Provenance recovery requires an operator-recorded reason",
            retryable=False,
        )
    if deps.file_exists(
        FileExistsRequest(schema_version="1.0", path=recovery_manifest), root_ctx
    ).exists:
        raise AppError(
            code="ingest_cohort_provenance_recovery_target_exists",
            message="Provenance recovery target manifest already exists",
            retryable=False,
        )

    manifest_size, files = _load_frozen_cohort(
        cohort_manifest=source_manifest,
        expected_size=None,
        deps=deps,
        root_ctx=root_ctx,
    )
    source_payload = json.loads(
        deps.read_text(
            ReadTextRequest(schema_version="1.0", path=source_manifest), root_ctx
        ).content
    )
    current_policy_hash = admission_policy_hash(settings)
    current_producer_build_identity = root_ctx.producer_commit_sha or "workspace"
    source_producer_build_identity = str(
        source_payload.get("producer_build_identity") or "workspace"
    )
    source_policy_hash = str(source_payload.get("policy_hash") or "")
    policy_changed = source_policy_hash != current_policy_hash
    producer_identity_changed = (
        source_producer_build_identity != current_producer_build_identity
    )
    if (policy_changed and not allow_policy_transition) or (
        producer_identity_changed and not allow_producer_transition
    ):
        raise AppError(
            code="ingest_cohort_provenance_recovery_incompatible",
            message=(
                "Frozen cohort policy or producer identity differs from the "
                "requested recovery runtime"
            ),
            retryable=False,
        )

    configuration_hash = admission_configuration_hash(settings)
    payload = dict(source_payload)
    payload["configuration_hash"] = configuration_hash
    payload["configuration_snapshot"] = admission_configuration_snapshot(settings)
    payload["policy_hash"] = current_policy_hash
    payload["producer_build_identity"] = current_producer_build_identity
    payload["validation_run_id"] = str(
        _validation_run_id_for_cohort(
            cohort_id=_cohort_id(files),
            configuration_hash=configuration_hash,
            policy_hash=current_policy_hash,
            producer_build_identity=current_producer_build_identity,
        )
    )
    payload["provenance_recovery"] = {
        "source_manifest": source_manifest,
        "source_validation_run_id": str(source_payload.get("validation_run_id") or ""),
        "source_configuration_hash": str(
            source_payload.get("configuration_hash") or ""
        ),
        "source_policy_hash": source_policy_hash,
        "policy_changed": policy_changed,
        "source_producer_build_identity": str(source_producer_build_identity),
        "producer_identity_changed": producer_identity_changed,
        "reason": recovery_reason.strip(),
        "recovered_at_utc": datetime.now(timezone.utc).isoformat(),
    }
    deps.write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=recovery_manifest,
            content=json.dumps(payload, sort_keys=True, indent=2).encode("utf-8"),
        ),
        root_ctx,
    )
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_cohort_provenance_recovery_created",
            module=logger.name,
            fields={
                "source_manifest": source_manifest,
                "recovery_manifest": recovery_manifest,
                "cohort_size": manifest_size,
                "cohort_id": _cohort_id(files),
                "validation_run_id": payload["validation_run_id"],
                "policy_changed": policy_changed,
                "producer_identity_changed": producer_identity_changed,
            },
        )
    )
    return files


def _frozen_cohort(
    *,
    cohort_size: int,
    cohort_manifest: str,
    selected_files: list[DriveFile],
    settings: IngestSettings,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
    admission_decisions: list[dict[str, Any]] | None = None,
) -> list[DriveFile]:
    """Load a replayable immutable cohort or persist it before processing."""
    if cohort_size < 1:
        raise AppError(
            code="ingest_cohort_size_invalid",
            message="Cohort size must be positive",
            retryable=False,
        )
    exists = deps.file_exists(
        FileExistsRequest(schema_version="1.0", path=cohort_manifest), root_ctx
    ).exists
    if exists:
        _manifest_size, files = _load_frozen_cohort(
            cohort_manifest=cohort_manifest,
            expected_size=cohort_size,
            expected_configuration_hash=admission_configuration_hash(settings),
            expected_policy_hash=admission_policy_hash(settings),
            expected_producer_build_identity=(
                root_ctx.producer_commit_sha or "workspace"
            ),
            deps=deps,
            root_ctx=root_ctx,
        )
        return files
    if len(selected_files) != cohort_size:
        raise AppError(
            code="ingest_cohort_insufficient_eligible_reports",
            message="Insufficient eligible reports to freeze the requested cohort",
            retryable=False,
            context={"requested": cohort_size, "selected": len(selected_files)},
        )
    decisions = admission_decisions or [
        {
            "file_id": file.file_id,
            "source_identity_id": file.md5_checksum or file.file_id,
            "title_key": _admission_title_key(file.name),
            "mime_type": (file.mime_type or "application/pdf").casefold(),
            "publisher_id": "unattributed",
            "source_url_classification": "drive_pdf",
            "runtime_dependency_status": "validated_pre_freeze",
            "budget_policy": "run_budget_enforced",
            "evidence_potential": "sufficient",
            "outcome": "admitted",
            "preflight_version": "2.0",
            "decision_hash": sha256(
                json.dumps(asdict(file), sort_keys=True, separators=(",", ":")).encode(
                    "utf-8"
                )
            ).hexdigest(),
        }
        for file in selected_files
    ]
    decisions_by_file_id = {
        str(decision.get("file_id") or ""): decision for decision in decisions
    }
    members = [
        {
            **asdict(file),
            "report_id": file.file_id,
            "source_identity_id": file.md5_checksum or file.file_id,
            "publisher_id": str(
                decisions_by_file_id.get(file.file_id, {}).get("publisher_id")
                or "unattributed"
            ),
            "selection_reason": "deterministic_admission_preflight",
        }
        for file in selected_files
    ]
    configuration_hash = admission_configuration_hash(settings)
    policy_hash = admission_policy_hash(settings)
    cohort_id = _cohort_id(selected_files)
    producer_build_identity = root_ctx.producer_commit_sha or "workspace"
    payload = {
        "schema_version": COHORT_MANIFEST_SCHEMA_VERSION,
        "cohort_id": cohort_id,
        "cohort_size": cohort_size,
        "configuration_hash": configuration_hash,
        "configuration_snapshot": admission_configuration_snapshot(settings),
        "policy_hash": policy_hash,
        "producer_build_identity": producer_build_identity,
        "validation_run_id": str(
            _validation_run_id_for_cohort(
                cohort_id=cohort_id,
                configuration_hash=configuration_hash,
                policy_hash=policy_hash,
                producer_build_identity=producer_build_identity,
            )
        ),
        "selection_reason": "deterministic_admission_preflight",
        "admission_preflight_version": "2.0",
        "admission_decision_hash": sha256(
            json.dumps(decisions, sort_keys=True, separators=(",", ":")).encode("utf-8")
        ).hexdigest(),
        "created_at_utc": datetime.now(timezone.utc).isoformat(),
        "members": members,
        "admission_decisions": decisions,
    }
    deps.write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=cohort_manifest,
            content=json.dumps(payload, sort_keys=True, indent=2).encode("utf-8"),
        ),
        root_ctx,
    )
    return selected_files


def _cohort_id(files: list[DriveFile]) -> str:
    """Return the immutable identity of the exact ordered admitted cohort."""
    members = [asdict(file) for file in files]
    return sha256(
        json.dumps(members, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()


def _validation_run_id_for_cohort(
    *,
    cohort_id: str,
    configuration_hash: str,
    policy_hash: str,
    producer_build_identity: str,
) -> ValidationRunId:
    """Bind a validation run to its complete immutable provenance identity."""

    identity = {
        "cohort_id": cohort_id,
        "configuration_hash": configuration_hash,
        "policy_hash": policy_hash,
        "producer_build_identity": producer_build_identity,
    }
    digest = sha256(
        json.dumps(identity, sort_keys=True, separators=(",", ":")).encode("utf-8")
    ).hexdigest()
    return ValidationRunId(f"validation:{digest}")


def _record_cohort_ingest_manifest(
    *,
    validation_run_id: ValidationRunId,
    settings: IngestSettings,
    root_ctx: RunContext,
    files: list[DriveFile],
    outcomes: list[IngestOutcome] | None = None,
    admission_decisions: list[dict[str, Any]] | None = None,
) -> None:
    configuration_hash = admission_configuration_hash(settings)
    policy_hash = admission_policy_hash(settings)
    cohort_id = _cohort_id(files)
    create_validation_run_manifest(
        ValidationRunManifestCreateRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            validation_run_id=validation_run_id,
            cohort_id=cohort_id,
            workflow_run_id=RunId(root_ctx.run_id),
            configuration_hash=configuration_hash,
            policy_hash=policy_hash,
            producer_build_identity=root_ctx.producer_commit_sha or "workspace",
            created_at_utc=datetime.now(timezone.utc).isoformat(),
        ),
        root_ctx,
    )
    timestamp = datetime.now(timezone.utc).isoformat()
    attempt_number = max(1, int(root_ctx.validation_attempt_number or 1))
    parent_attempt_number = max(0, int(root_ctx.validation_parent_attempt_number or 0))
    decisions_by_file_id = {
        str(decision.get("file_id") or ""): decision
        for decision in admission_decisions or []
    }

    def _publisher_id(file: DriveFile) -> str:
        decision = decisions_by_file_id.get(file.file_id, {})
        return str(decision.get("publisher_id") or "unattributed")

    if outcomes is None:
        for file in files:
            publisher_id = _publisher_id(file)
            for stage in (
                "discovery",
                "candidate_qualification",
                "admission_preflight",
            ):
                record_validation_run_manifest_stage(
                    ValidationRunManifestRecordRequest(
                        schema_version="1.0",
                        db_path=settings.reports_db,
                        record=ValidationRunManifestStageRecord(
                            schema_version="1.0",
                            validation_run_id=validation_run_id,
                            cohort_id=cohort_id,
                            workflow_run_id=RunId(root_ctx.run_id),
                            entity_type="report",
                            publisher_id=publisher_id,
                            report_id=file.file_id,
                            source_identity_id=file.md5_checksum or file.file_id,
                            stage=stage,
                            attempt_number=attempt_number,
                            parent_attempt_number=parent_attempt_number,
                            input_artifact_ids=(file.file_id,),
                            output_artifact_ids=(cohort_id,),
                            started_at_utc=timestamp,
                            completed_at_utc=timestamp,
                            terminal_outcome="succeeded",
                            failure_code="",
                            retryable=False,
                            repair_disposition="not_required",
                            duplicate_disposition="new",
                            supersession_state="current",
                            idempotency_state="new",
                            configuration_hash=configuration_hash,
                            policy_hash=policy_hash,
                            producer_build_identity=root_ctx.producer_commit_sha
                            or "workspace",
                            cohort_disposition="final_validation",
                            entity_terminal=False,
                        ),
                    ),
                    root_ctx,
                )
        return
    outcome_by_id = {outcome.file_id: outcome for outcome in outcomes or []}
    for file in files:
        publisher_id = _publisher_id(file)
        outcome = outcome_by_id.get(file.file_id)
        terminal = outcome is not None
        readiness_status = (
            str(outcome.publish_readiness_status if outcome else "").strip().casefold()
        )
        reused_validated_html_path = (
            outcome.html_path
            if outcome
            and outcome.status == "skipped"
            and outcome.error == "html_exists"
            and outcome.html_path
            and readiness_status == "pass"
            else None
        )
        successful = bool(
            outcome
            and (
                (outcome.status == "processed" and readiness_status == "pass")
                or reused_validated_html_path
            )
        )
        terminal_outcome = (
            "publish_ready"
            if successful
            else "permanent_failure"
            if terminal
            else "blocked"
        )
        if terminal and not successful:
            _record_failed_cohort_stage_closure(
                validation_run_id=validation_run_id,
                settings=settings,
                root_ctx=root_ctx,
                file=file,
                cohort_id=cohort_id,
                configuration_hash=configuration_hash,
                policy_hash=policy_hash,
                timestamp=timestamp,
                attempt_number=attempt_number,
                parent_attempt_number=parent_attempt_number,
                publisher_id=publisher_id,
                failure_code=(
                    outcome.error
                    or (
                        "publish_readiness_unverified"
                        if not readiness_status
                        else f"publish_readiness_{readiness_status}"
                    )
                )
                if outcome
                else "ingest_failed",
            )
        elif reused_validated_html_path:
            _record_reused_cohort_stage_closure(
                validation_run_id=validation_run_id,
                settings=settings,
                root_ctx=root_ctx,
                file=file,
                cohort_id=cohort_id,
                configuration_hash=configuration_hash,
                policy_hash=policy_hash,
                timestamp=timestamp,
                attempt_number=attempt_number,
                parent_attempt_number=parent_attempt_number,
                publisher_id=publisher_id,
                html_path=reused_validated_html_path,
            )
        record_validation_run_manifest_stage(
            ValidationRunManifestRecordRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                record=ValidationRunManifestStageRecord(
                    schema_version="1.0",
                    validation_run_id=validation_run_id,
                    cohort_id=cohort_id,
                    workflow_run_id=RunId(root_ctx.run_id),
                    entity_type="report",
                    publisher_id=publisher_id,
                    report_id=file.file_id,
                    source_identity_id=file.md5_checksum or file.file_id,
                    stage="ingestion",
                    attempt_number=attempt_number,
                    parent_attempt_number=parent_attempt_number,
                    input_artifact_ids=(file.file_id,),
                    output_artifact_ids=(
                        (outcome.html_path,) if outcome and outcome.html_path else ()
                    ),
                    started_at_utc=timestamp,
                    completed_at_utc=timestamp,
                    terminal_outcome=terminal_outcome,
                    failure_code=(
                        (
                            outcome.error
                            or (
                                ""
                                if successful
                                else (
                                    "publish_readiness_unverified"
                                    if not readiness_status
                                    else f"publish_readiness_{readiness_status}"
                                )
                            )
                        )
                        if outcome
                        else "cohort_report_missing"
                    ),
                    retryable=False,
                    repair_disposition="none",
                    duplicate_disposition="none",
                    supersession_state="current",
                    idempotency_state="new",
                    configuration_hash=configuration_hash,
                    policy_hash=policy_hash,
                    producer_build_identity=root_ctx.producer_commit_sha or "workspace",
                    cohort_disposition="final_validation",
                    entity_terminal=terminal,
                ),
            ),
            root_ctx,
        )


def _record_failed_cohort_stage_closure(
    *,
    validation_run_id: ValidationRunId,
    settings: IngestSettings,
    root_ctx: RunContext,
    file: DriveFile,
    cohort_id: str,
    configuration_hash: str,
    policy_hash: str,
    timestamp: str,
    attempt_number: int,
    parent_attempt_number: int,
    publisher_id: str,
    failure_code: str,
) -> None:
    """Close unreachable stages explicitly for a terminal failed cohort member.

    A fixed validation cohort must retain a status for every mandatory stage even
    when an earlier source or generation failure makes downstream work unsafe.
    Existing successful stage records are idempotently retained by the manifest
    service; only the not-reached stages become ``blocked``.
    """
    for stage in (
        "acquisition",
        "source_preparation",
        "source_validation",
        "evidence_generation",
        "structured_output_repair",
        "taxonomy",
        "category_fit",
        "artifact_generation",
        "regeneration",
        "grounding_validation",
        "semantic_validation",
        "rendering",
        "final_html_validation",
        "publication_preflight",
        "wordpress_lookup",
        "wordpress_write",
        "authenticated_readback",
        "repeat_publication",
    ):
        record_validation_run_manifest_stage(
            ValidationRunManifestRecordRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                record=ValidationRunManifestStageRecord(
                    schema_version="1.0",
                    validation_run_id=validation_run_id,
                    cohort_id=cohort_id,
                    workflow_run_id=RunId(root_ctx.run_id),
                    entity_type="report",
                    publisher_id=publisher_id,
                    report_id=file.file_id,
                    source_identity_id=file.md5_checksum or file.file_id,
                    stage=stage,
                    attempt_number=attempt_number,
                    parent_attempt_number=parent_attempt_number,
                    input_artifact_ids=(file.file_id,),
                    output_artifact_ids=(),
                    started_at_utc=timestamp,
                    completed_at_utc=timestamp,
                    terminal_outcome="blocked",
                    failure_code=failure_code,
                    retryable=False,
                    repair_disposition="not_required",
                    duplicate_disposition="none",
                    supersession_state="current",
                    idempotency_state="new",
                    configuration_hash=configuration_hash,
                    policy_hash=policy_hash,
                    producer_build_identity=root_ctx.producer_commit_sha or "workspace",
                    cohort_disposition="final_validation",
                    entity_terminal=False,
                ),
            ),
            root_ctx,
        )


def _record_reused_cohort_stage_closure(
    *,
    validation_run_id: ValidationRunId,
    settings: IngestSettings,
    root_ctx: RunContext,
    file: DriveFile,
    cohort_id: str,
    configuration_hash: str,
    policy_hash: str,
    timestamp: str,
    attempt_number: int,
    parent_attempt_number: int,
    publisher_id: str,
    html_path: str,
) -> None:
    """Record the validated artifact reuse that closes an idempotent replay."""
    for stage in (
        "acquisition",
        "source_preparation",
        "source_validation",
        "evidence_generation",
        "structured_output_repair",
        "taxonomy",
        "category_fit",
        "artifact_generation",
        "regeneration",
        "grounding_validation",
        "semantic_validation",
        "rendering",
        "final_html_validation",
    ):
        record_validation_run_manifest_stage(
            ValidationRunManifestRecordRequest(
                schema_version="1.0",
                db_path=settings.reports_db,
                record=ValidationRunManifestStageRecord(
                    schema_version="1.0",
                    validation_run_id=validation_run_id,
                    cohort_id=cohort_id,
                    workflow_run_id=RunId(root_ctx.run_id),
                    entity_type="report",
                    publisher_id=publisher_id,
                    report_id=file.file_id,
                    source_identity_id=file.md5_checksum or file.file_id,
                    stage=stage,
                    attempt_number=attempt_number,
                    parent_attempt_number=parent_attempt_number,
                    input_artifact_ids=(file.file_id,),
                    output_artifact_ids=(html_path,) if html_path else (),
                    started_at_utc=timestamp,
                    completed_at_utc=timestamp,
                    terminal_outcome="succeeded",
                    failure_code="",
                    retryable=False,
                    repair_disposition="not_required",
                    duplicate_disposition="reused",
                    supersession_state="current",
                    idempotency_state="reused",
                    configuration_hash=configuration_hash,
                    policy_hash=policy_hash,
                    producer_build_identity=root_ctx.producer_commit_sha or "workspace",
                    cohort_disposition="final_validation",
                    entity_terminal=False,
                ),
            ),
            root_ctx,
        )


def _report_card_backfill_should_skip(
    file: DriveFile,
    *,
    settings: IngestSettings,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
) -> bool:
    metadata = deps.get_report_metadata(
        ReportMetadataGetRequest(
            schema_version="1.0",
            db_path=settings.reports_db,
            file_id=file.file_id,
        ),
        root_ctx,
    )
    html_path = str(metadata.html_path or "").strip() if metadata else ""
    if html_path:
        manifest_path = Path(html_path).with_suffix("") / "report-card-manifest.json"
        manifest_path_source = "report_metadata"
    else:
        manifest_path = (
            Path(settings.output_dir)
            / report_slug(file.name or file.file_id, file.file_id)
            / "report-card-manifest.json"
        )
        manifest_path_source = "report_slug_fallback"
    if not deps.file_exists(
        FileExistsRequest(schema_version="1.0", path=str(manifest_path)), root_ctx
    ).exists:
        decision = "reprocess"
        reason = "manifest_missing"
    else:
        try:
            content = deps.read_text(
                ReadTextRequest(schema_version="1.0", path=str(manifest_path)),
                root_ctx,
            ).content
            payload = json.loads(content)
            if not isinstance(payload, dict):
                raise AppError(
                    code="cover_asset_set_incomplete",
                    message="Report-card manifest must contain a JSON object",
                    retryable=False,
                )
            ReportCardManifest.from_dict(payload)
        except json.JSONDecodeError:
            decision = "reprocess"
            reason = "manifest_invalid_json"
        except AppError as exc:
            if exc.retryable:
                raise
            decision = "reprocess"
            reason = exc.code
        else:
            decision = "skip"
            reason = "manifest_valid"
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_report_card_backfill_decision",
            module=logger.name,
            fields={
                "file_id": file.file_id,
                "decision": decision,
                "reason": reason,
                "manifest_path": str(manifest_path),
                "manifest_path_source": manifest_path_source,
            },
        )
    )
    return decision == "skip"


def _resolve_worker_limit(
    settings: IngestSettings,
    *,
    file_count: int,
    root_ctx: RunContext,
) -> int:
    worker_limit = settings.ingest_worker_limit
    try:
        worker_limit = int(worker_limit)
    except (TypeError, ValueError):
        worker_limit = 1
    if worker_limit < 1:
        worker_limit = 1
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_worker_config",
            module=logger.name,
            fields={
                "worker_limit": worker_limit,
                "file_count": file_count,
            },
        )
    )
    return worker_limit


@dataclass(frozen=True)
class _DriveCachePrefetchResult:
    file_id: str
    cache_path: str
    md5: str | None
    status: str
    reason: str


def _should_run_drive_cache_prefetch(deps: IngestBatchDependencies) -> bool:
    return deps.process_file is _process_file


def _prefetch_cached_pdf(
    file: DriveFile,
    *,
    settings: IngestSettings,
    root_ctx: RunContext,
) -> _DriveCachePrefetchResult:
    prefetch_ctx = child_context(root_ctx, task_id=f"prefetch:{file.file_id}")
    cache_path = _cache_pdf_path(settings, file)
    drive_md5 = file.md5_checksum.strip() if file.md5_checksum else None

    def _write_sidecar(md5: str | None, stat_resp) -> None:
        write_md5_sidecar(
            FileCacheMd5SidecarWriteRequest(
                schema_version="1.0",
                cache_path=cache_path,
                file_id=file.file_id,
                file_name=file.name,
                md5=md5,
                size_bytes=stat_resp.size_bytes,
                mtime_utc=stat_resp.mtime_utc,
            ),
            prefetch_ctx,
        )

    stat_resp = file_stat(
        FileStatRequest(schema_version="1.0", path=cache_path), prefetch_ctx
    )
    if stat_resp.exists:
        sidecar = resolve_md5_sidecar(
            FileCacheMd5SidecarResolveRequest(
                schema_version="1.0",
                cache_path=cache_path,
                file_id=file.file_id,
                size_bytes=stat_resp.size_bytes,
                mtime_utc=stat_resp.mtime_utc,
            ),
            prefetch_ctx,
        )
        if sidecar.resolved_md5 and (
            not drive_md5 or sidecar.resolved_md5 == drive_md5
        ):
            return _DriveCachePrefetchResult(
                file_id=file.file_id,
                cache_path=cache_path,
                md5=sidecar.resolved_md5,
                status="hit",
                reason="sidecar",
            )
        hashed_stat = file_stat(
            FileStatRequest(schema_version="1.0", path=cache_path, compute_md5=True),
            prefetch_ctx,
        )
        if (
            hashed_stat.exists
            and hashed_stat.md5
            and (not drive_md5 or hashed_stat.md5 == drive_md5)
        ):
            _write_sidecar(hashed_stat.md5, hashed_stat)
            return _DriveCachePrefetchResult(
                file_id=file.file_id,
                cache_path=cache_path,
                md5=hashed_stat.md5,
                status="hit",
                reason="hashed",
            )

    dl_req = DriveDownloadToPathRequest(
        schema_version="1.0",
        file=file,
        service_account_path=settings.google_sa_path,
        auth_mode=settings.drive_auth_mode,
        oauth_client_path=settings.google_oauth_client_path,
        oauth_token_path=settings.google_oauth_token_path,
        output_path=cache_path,
        run_budget=_ingest_run_budget(settings, prefetch_ctx),
    )
    attempt = 0
    eof_check = None
    while True:
        dl_resp = _run_step_with_retry(
            "prefetch_download_pdf",
            prefetch_ctx,
            lambda: download_pdf_to_path(dl_req, prefetch_ctx),
            2,
        )
        eof_check = check_pdf_eof(
            PdfEofCheckRequest(schema_version="1.0", path=cache_path),
            prefetch_ctx,
        )
        if eof_check.has_eof or attempt >= EOF_RETRY_LIMIT:
            break
        delete_file(
            DeleteFileRequest(
                schema_version="1.0",
                path=cache_path,
                missing_ok=True,
            ),
            prefetch_ctx,
        )
        attempt += 1
    if eof_check is None or not eof_check.has_eof:
        delete_file(
            DeleteFileRequest(
                schema_version="1.0",
                path=cache_path,
                missing_ok=True,
            ),
            prefetch_ctx,
        )
        logger.info(
            log_event(
                prefetch_ctx,
                role="orchestrator",
                event="ingest_drive_cache_prefetch_rejected_missing_pdf_eof",
                module=logger.name,
                fields={
                    "file_id": file.file_id,
                    "md5": drive_md5 or "",
                    "cache_path": cache_path,
                    "attempt_count": attempt + 1,
                    "reason": "missing_pdf_eof_after_bounded_retries",
                },
            )
        )
        return _DriveCachePrefetchResult(
            file_id=file.file_id,
            cache_path=cache_path,
            md5=drive_md5,
            status="rejected",
            reason="missing_pdf_eof_after_bounded_retries",
        )
    final_stat = file_stat(
        FileStatRequest(schema_version="1.0", path=cache_path, compute_md5=True),
        prefetch_ctx,
    )
    md5 = final_stat.md5 or dl_resp.md5 or drive_md5
    _write_sidecar(md5, final_stat)
    return _DriveCachePrefetchResult(
        file_id=file.file_id,
        cache_path=cache_path,
        md5=md5,
        status="downloaded",
        reason="missing_or_stale",
    )


def _prefetch_drive_cache_stage(
    files_to_process: list[DriveFile],
    *,
    settings: IngestSettings,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
) -> list[DriveFile]:
    if not files_to_process or not _should_run_drive_cache_prefetch(deps):
        return files_to_process
    worker_limit = min(
        max(1, int(settings.ingest_worker_limit or 1)),
        len(files_to_process),
    )
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_drive_cache_prefetch_start",
            module=logger.name,
            fields={
                "file_count": len(files_to_process),
                "drive_cache_worker_limit": worker_limit,
                "report_worker_limit": settings.report_worker_limit,
                "llm_worker_limit": settings.ingest_worker_limit,
            },
        )
    )
    results: list[_DriveCachePrefetchResult] = []
    if worker_limit <= 1:
        for file in files_to_process:
            results.append(
                _prefetch_cached_pdf(file, settings=settings, root_ctx=root_ctx)
            )
    else:
        with deps.thread_pool_executor_factory(worker_limit) as executor:
            futures = {
                executor.submit(
                    _prefetch_cached_pdf,
                    file,
                    settings=settings,
                    root_ctx=root_ctx,
                ): file
                for file in files_to_process
            }
            for future in as_completed(futures):
                results.append(future.result())
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_drive_cache_prefetch_complete",
            module=logger.name,
            fields={
                "file_count": len(results),
                "cache_hits": sum(1 for result in results if result.status == "hit"),
                "downloaded": sum(
                    1 for result in results if result.status == "downloaded"
                ),
                "rejected": sum(1 for result in results if result.status == "rejected"),
                "md5_available": sum(1 for result in results if result.md5),
            },
        )
    )
    results_by_file_id = {result.file_id: result for result in results}
    resolved_files = [
        replace(
            file,
            md5_checksum=(results_by_file_id[file.file_id].md5 or file.md5_checksum),
        )
        if results_by_file_id.get(file.file_id)
        else file
        for file in files_to_process
    ]
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_drive_cache_prefetch_source_identity_enriched",
            module=logger.name,
            fields={
                "file_count": len(resolved_files),
                "source_identity_enriched": sum(
                    1
                    for original, resolved in zip(
                        files_to_process, resolved_files, strict=True
                    )
                    if not original.md5_checksum and resolved.md5_checksum
                ),
            },
        )
    )
    return resolved_files


def _process_ingest_batch(
    files_to_process: list[DriveFile],
    *,
    settings: IngestSettings,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
    force_report_cards: bool,
    start_index: int = 0,
    runtime_preflight_passed: bool = True,
    runtime_preflight_hash: str = "",
    admission_decisions: list[dict[str, Any]] | None = None,
    admission_already_decided: bool = False,
) -> list[_FileProcessResult]:
    files_to_process = _prefetch_drive_cache_stage(
        files_to_process,
        settings=settings,
        deps=deps,
        root_ctx=root_ctx,
    )
    positions = {
        file.file_id: index
        for index, file in enumerate(files_to_process, start=start_index)
    }
    decisions = list(admission_decisions or [])
    admitted = files_to_process
    enforce_source_admission = _should_run_drive_cache_prefetch(deps) or bool(
        admission_already_decided
    )
    if enforce_source_admission and (not admission_already_decided or not decisions):
        decisions = []
        admitted = _cohort_admission_preflight(
            files_to_process,
            settings=settings,
            deps=deps,
            root_ctx=root_ctx,
            admission_decisions=decisions,
            runtime_preflight_passed=runtime_preflight_passed,
            runtime_preflight_hash=runtime_preflight_hash,
        )
        _persist_admission_funnel(
            decisions,
            settings=settings,
            deps=deps,
            root_ctx=root_ctx,
        )
    decisions_by_file_id = {
        str(row.get("file_id") or ""): row for row in decisions if row.get("file_id")
    }
    admitted_ids = {file.file_id for file in admitted}
    results: list[_FileProcessResult] = []
    for file in files_to_process:
        if file.file_id in admitted_ids:
            continue
        row = decisions_by_file_id.get(file.file_id, {})
        outcome = str(row.get("outcome") or "policy_blocked")
        results.append(
            _FileProcessResult(
                index=positions[file.file_id],
                outcome=IngestOutcome(
                    schema_version="1.0",
                    file_id=file.file_id,
                    name=file.name or file.file_id,
                    md5=file.md5_checksum,
                    html_path=None,
                    status="skipped",
                    error=f"admission_{outcome}",
                ),
                processed=0,
                had_error=False,
            )
        )
    files_to_process = admitted

    def _admitted_context(file: DriveFile) -> RunContext:
        row = decisions_by_file_id.get(file.file_id, {})
        return replace(
            root_ctx,
            source_identity_id=str(
                row.get("source_identity_id") or file.md5_checksum or file.file_id
            ),
            publisher_id=str(row.get("publisher_id") or "drive_unattributed"),
            admission_decision_hash=str(row.get("decision_hash") or ""),
        )

    worker_limit = _resolve_worker_limit(
        settings,
        file_count=len(files_to_process),
        root_ctx=root_ctx,
    )
    if worker_limit <= 1 or len(files_to_process) <= 1:
        for file in files_to_process:
            idx = positions[file.file_id]
            results.append(
                deps.process_file(
                    file,
                    idx,
                    settings,
                    _admitted_context(file),
                    force_report_cards,
                )
            )
        return results

    with deps.thread_pool_executor_factory(worker_limit) as executor:
        futures = {
            executor.submit(
                deps.process_file,
                file,
                positions[file.file_id],
                settings,
                _admitted_context(file),
                force_report_cards,
            ): (
                positions[file.file_id],
                file,
            )
            for file in files_to_process
        }
        for future in as_completed(futures):
            idx, file = futures[future]
            try:
                result = future.result()
            except (
                AppError,
                OSError,
                RuntimeError,
                ValueError,
                TypeError,
            ) as exc:  # pragma: no cover - defensive fallback
                file_ctx = child_context(root_ctx, task_id=file.file_id)
                record_workflow_failure(
                    state_db=settings.state_db,
                    workflow="ingest",
                    stage="batch_file_worker",
                    operation="process_file",
                    error=exc,
                    ctx=file_ctx,
                    input_checksum=file.md5_checksum
                    or remediation_input_checksum(
                        {"file_id": file.file_id, "name": file.name}
                    ),
                    report_id=file.file_id,
                    source_id=_cache_pdf_path(settings, file),
                )
                logger.info(
                    log_event(
                        file_ctx,
                        role="orchestrator",
                        event="file_processing_error",
                        module=logger.name,
                        fields={
                            "file_id": file.file_id,
                            "error": str(exc),
                            "local_path": _cache_pdf_path(settings, file),
                            "md5": file.md5_checksum or "",
                        },
                    )
                )
                result = _FileProcessResult(
                    index=idx,
                    outcome=IngestOutcome(
                        schema_version="1.0",
                        file_id=file.file_id,
                        name=file.name or file.file_id,
                        md5=None,
                        html_path=None,
                        status="error",
                        error=str(exc),
                    ),
                    processed=0,
                    had_error=True,
                )
            results.append(result)
    return results


def _persist_admission_funnel(
    decisions: list[dict[str, Any]],
    *,
    settings: IngestSettings,
    deps: IngestBatchDependencies,
    root_ctx: RunContext,
) -> None:
    """Retain every selected candidate outside the admitted-cohort denominator."""

    if not decisions:
        return
    decision_hash = sha256(
        json.dumps(
            decisions,
            ensure_ascii=True,
            sort_keys=True,
            separators=(",", ":"),
        ).encode("utf-8")
    ).hexdigest()
    path = (
        Path(settings.output_dir)
        / "admission"
        / f"{root_ctx.run_id}-{decision_hash[:16]}.json"
    )
    payload = {
        "schema_version": "1.0",
        "run_id": str(root_ctx.run_id),
        "configuration_hash": admission_configuration_hash(settings),
        "policy_hash": admission_policy_hash(settings),
        "decision_set_hash": decision_hash,
        "decisions": decisions,
    }
    deps.write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=str(path),
            content=json.dumps(
                payload,
                ensure_ascii=True,
                sort_keys=True,
                indent=2,
            ).encode("utf-8"),
            make_parents=True,
        ),
        root_ctx,
    )
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_admission_funnel_persisted",
            module=logger.name,
            fields={
                "decision_count": len(decisions),
                "admitted_count": sum(
                    1 for decision in decisions if decision.get("outcome") == "admitted"
                ),
                "rejected_count": sum(
                    1 for decision in decisions if decision.get("outcome") != "admitted"
                ),
                "decision_set_hash": decision_hash,
            },
        )
    )


def _update_ingest_cursor(
    settings: IngestSettings,
    *,
    processed: int,
    had_errors: bool,
    attempt_limit: Optional[int],
    root_ctx: RunContext,
) -> None:
    if not had_errors and processed > 0 and attempt_limit is None:
        try:
            now_utc = (
                datetime.now(timezone.utc)
                .replace(microsecond=0)
                .isoformat()
                .replace("+00:00", "Z")
            )
            set_ingest_cursor(
                StateIngestCursorSetRequest(
                    schema_version="1.0",
                    state_db=settings.state_db,
                    last_successful_ingest_utc=now_utc,
                ),
                root_ctx,
            )
            logger.info(
                log_event(
                    root_ctx,
                    role="orchestrator",
                    event="ingest_cursor_updated",
                    module=logger.name,
                    fields={"last_successful_ingest_utc": now_utc},
                )
            )
        except AppError as exc:
            logger.info(
                log_event(
                    root_ctx,
                    role="orchestrator",
                    event="ingest_cursor_update_failed",
                    module=logger.name,
                    fields={"error": str(exc)},
                )
            )
        return
    logger.info(
        log_event(
            root_ctx,
            role="orchestrator",
            event="ingest_cursor_skipped",
            module=logger.name,
            fields={
                "reason": "errors_detected"
                if had_errors
                else "no_processed_or_attempt_limit_override",
                "processed": processed,
                "attempt_limit": attempt_limit,
            },
        )
    )


def _finalize_usage_projection(settings: IngestSettings, root_ctx: RunContext) -> None:
    """Materialize canonical usage without masking the ingest result."""
    if not file_exists(
        FileExistsRequest(schema_version="1.0", path=settings.usage_db_path), root_ctx
    ).exists:
        return
    try:
        status = finalize_usage_projection(
            LLMUsageProjectionStatusRequest(
                schema_version="1.0",
                db_path=settings.usage_db_path,
                ledger_path=settings.cost_ledger_path,
                daily_path=settings.cost_daily_path,
            ),
            root_ctx,
        )
        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_usage_projection_finalized",
                module=logger.name,
                fields={
                    "latest_event_id": status.latest_event_id,
                    "pending_event_count": status.pending_event_count,
                    "files_valid": status.files_valid,
                },
            )
        )
    except AppError as exc:
        logger.warning(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_usage_projection_finalize_failed",
                module=logger.name,
                fields={"error_code": exc.code, "retryable": exc.retryable},
            )
        )


def run_ingest(
    settings: IngestSettings,
    *,
    folder_id: Optional[str] = None,
    attempt_limit: Optional[int] = None,
    limit: Optional[int] = None,
    cohort_size: Optional[int] = None,
    cohort_manifest: Optional[str] = None,
    success_target: Optional[int] = None,
    ctx: Optional[RunContext] = None,
    dependencies: Optional[IngestBatchDependencies] = None,
    force_report_cards: bool = False,
    rescan: bool = False,
) -> List[IngestOutcome]:
    if attempt_limit is not None and limit is not None:
        raise AppError(
            code="ingest_attempt_limit_conflict",
            message="Provide either attempt_limit or the deprecated limit, not both",
            retryable=False,
        )
    resolved_attempt_limit = attempt_limit if attempt_limit is not None else limit
    if resolved_attempt_limit is not None and resolved_attempt_limit < 1:
        raise AppError(
            code="ingest_attempt_limit_invalid",
            message="Attempt limit must be positive",
            retryable=False,
        )
    deps = dependencies or IngestBatchDependencies.default()
    root_ctx = ctx or new_run_context()
    lock_ctx = child_context(root_ctx, task_id="ingest_lock")
    lock_info = None
    validation_run_id: ValidationRunId | None = None
    try:
        lock_info = acquire_ingest_lock(settings, lock_ctx)
        verify_ingest_db_access(settings, root_ctx)
        root_ctx = replace(
            root_ctx,
            workflow="report_generation",
            stage="admission_preflight",
            artifact_family="report",
            configuration_hash=admission_configuration_hash(settings),
            policy_hash=admission_policy_hash(settings),
        )
        runtime_preflight = preflight_report_pipeline(settings, root_ctx)
        runtime_preflight_passed = bool(runtime_preflight.passed)
        runtime_preflight_decision_hash = pipeline_preflight_decision_hash(
            runtime_preflight
        )

        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_start",
                module=logger.name,
                fields={
                    "folder_id": folder_id or settings.gdrive_folder_id,
                    "attempt_limit": resolved_attempt_limit,
                    "legacy_limit_used": limit is not None,
                    "cohort_size": cohort_size,
                    "cohort_manifest": cohort_manifest or "",
                    "success_target": success_target,
                    "force_report_cards": force_report_cards,
                    "rescan": rescan,
                    "runtime_preflight_passed": runtime_preflight_passed,
                    "runtime_preflight_hash": runtime_preflight_decision_hash,
                },
            )
        )

        modified_after = _resolve_modified_after(
            settings,
            limit=resolved_attempt_limit,
            force_report_cards=force_report_cards,
            rescan=rescan,
            root_ctx=root_ctx,
        )
        manifest_files: list[DriveFile] | None = None
        if cohort_manifest:
            manifest_exists = deps.file_exists(
                FileExistsRequest(schema_version="1.0", path=cohort_manifest), root_ctx
            ).exists
            if manifest_exists:
                cohort_size, manifest_files = _load_frozen_cohort(
                    cohort_manifest=cohort_manifest,
                    expected_size=cohort_size,
                    expected_configuration_hash=admission_configuration_hash(settings),
                    expected_policy_hash=admission_policy_hash(settings),
                    expected_producer_build_identity=(
                        root_ctx.producer_commit_sha or "workspace"
                    ),
                    deps=deps,
                    root_ctx=root_ctx,
                )
            elif cohort_size is None:
                raise AppError(
                    code="ingest_cohort_size_required",
                    message="Creating a cohort manifest requires a cohort size",
                    retryable=False,
                )
        selected_modes = sum(
            value is not None
            for value in (resolved_attempt_limit, cohort_size, success_target)
        )
        if selected_modes > 1:
            raise AppError(
                code="ingest_selection_mode_conflict",
                message=(
                    "Attempt limit, cohort size, and success target are mutually "
                    "exclusive"
                ),
                retryable=False,
            )
        selection_limit = (
            cohort_size if cohort_size is not None else resolved_attempt_limit
        )
        max_n = selection_limit if selection_limit is not None else settings.batch_limit
        list_req = _build_drive_list_request(
            settings,
            folder_id=folder_id,
            limit=selection_limit,
            modified_after=modified_after,
            ctx=root_ctx,
        )
        if success_target is not None:
            if success_target < 1:
                raise AppError(
                    code="ingest_success_target_invalid",
                    message="Success target must be positive",
                    retryable=False,
                )
            attempted_file_ids: set[str] = set()
            results: list[_FileProcessResult] = []
            processed_so_far = 0
            while processed_so_far < success_target:
                remaining = success_target - processed_so_far
                excluded = set(attempted_file_ids)
                files_to_process = _run_step_with_retry(
                    "materialize_drive_files",
                    root_ctx,
                    lambda current_remaining=remaining, current_excluded=excluded: (
                        _materialize_files_to_process(
                            list_req,
                            settings=settings,
                            max_n=current_remaining,
                            deps=deps,
                            root_ctx=root_ctx,
                            force_report_cards=force_report_cards,
                            excluded_file_ids=current_excluded,
                        )
                    ),
                    2,
                )
                if not files_to_process:
                    break
                attempted_file_ids.update(file.file_id for file in files_to_process)
                batch = _process_ingest_batch(
                    files_to_process,
                    settings=settings,
                    deps=deps,
                    root_ctx=root_ctx,
                    force_report_cards=force_report_cards,
                    start_index=len(results),
                    runtime_preflight_passed=runtime_preflight_passed,
                    runtime_preflight_hash=runtime_preflight_decision_hash,
                )
                results.extend(batch)
                processed_so_far += sum(row.processed for row in batch)
        else:
            files_to_process = manifest_files
            admission_decisions: list[dict[str, Any]] | None = None
            if cohort_size is not None:
                if manifest_files is None:
                    files_to_process, admission_decisions = _run_step_with_retry(
                        "select_admitted_cohort",
                        root_ctx,
                        lambda: _select_admitted_cohort(
                            cohort_size=cohort_size,
                            list_req=list_req,
                            settings=settings,
                            deps=deps,
                            root_ctx=root_ctx,
                            force_report_cards=force_report_cards,
                            runtime_preflight_passed=runtime_preflight_passed,
                            runtime_preflight_hash=runtime_preflight_decision_hash,
                        ),
                        2,
                    )
                manifest_path = cohort_manifest or str(
                    Path(settings.output_dir) / "cohorts" / f"{root_ctx.run_id}.json"
                )
                files_to_process = _frozen_cohort(
                    cohort_size=cohort_size,
                    cohort_manifest=manifest_path,
                    selected_files=files_to_process,
                    settings=settings,
                    deps=deps,
                    root_ctx=root_ctx,
                    admission_decisions=admission_decisions,
                )
            elif files_to_process is None:
                files_to_process = _run_step_with_retry(
                    "materialize_drive_files",
                    root_ctx,
                    lambda: _materialize_files_to_process(
                        list_req,
                        settings=settings,
                        deps=deps,
                        root_ctx=root_ctx,
                        max_n=max_n,
                        force_report_cards=force_report_cards,
                    ),
                    2,
                )
            if cohort_size is not None:
                cohort_id = _cohort_id(files_to_process)
                configuration_hash = admission_configuration_hash(settings)
                policy_hash = admission_policy_hash(settings)
                validation_run_id = _validation_run_id_for_cohort(
                    cohort_id=cohort_id,
                    configuration_hash=configuration_hash,
                    policy_hash=policy_hash,
                    producer_build_identity=root_ctx.producer_commit_sha or "workspace",
                )
                root_ctx = replace(
                    root_ctx,
                    validation_run_id=str(validation_run_id),
                    cohort_id=cohort_id,
                    workflow="report_generation",
                    stage="ingest",
                    artifact_family="report",
                    configuration_hash=configuration_hash,
                    policy_hash=policy_hash,
                )
                create_validation_run_manifest(
                    ValidationRunManifestCreateRequest(
                        schema_version="1.0",
                        db_path=settings.reports_db,
                        validation_run_id=validation_run_id,
                        cohort_id=cohort_id,
                        workflow_run_id=RunId(root_ctx.run_id),
                        configuration_hash=configuration_hash,
                        policy_hash=policy_hash,
                        producer_build_identity=root_ctx.producer_commit_sha
                        or "workspace",
                        created_at_utc=datetime.now(timezone.utc).isoformat(),
                    ),
                    root_ctx,
                )
                attempt = resolve_validation_run_manifest_attempt(
                    ValidationRunManifestAttemptResolveRequest(
                        schema_version="1.0",
                        db_path=settings.reports_db,
                        validation_run_id=validation_run_id,
                        mode="next_replay",
                    ),
                    root_ctx,
                )
                root_ctx = replace(
                    root_ctx,
                    validation_attempt_number=attempt.attempt_number,
                    validation_parent_attempt_number=attempt.parent_attempt_number,
                )
                _record_cohort_ingest_manifest(
                    validation_run_id=validation_run_id,
                    settings=settings,
                    root_ctx=root_ctx,
                    files=files_to_process,
                    admission_decisions=admission_decisions,
                )
            results = _process_ingest_batch(
                files_to_process,
                settings=settings,
                deps=deps,
                root_ctx=root_ctx,
                force_report_cards=force_report_cards,
                runtime_preflight_passed=runtime_preflight_passed,
                runtime_preflight_hash=runtime_preflight_decision_hash,
                admission_decisions=admission_decisions,
                admission_already_decided=cohort_size is not None
                and admission_decisions is not None,
            )
        results.sort(key=lambda r: r.index)
        outcomes = [result.outcome for result in results]
        if validation_run_id is not None:
            _record_cohort_ingest_manifest(
                validation_run_id=validation_run_id,
                settings=settings,
                root_ctx=root_ctx,
                files=files_to_process,
                outcomes=outcomes,
                admission_decisions=admission_decisions,
            )
            manifest_audit = audit_validation_run_manifest(
                ValidationRunManifestAuditRequest(
                    schema_version="1.0",
                    db_path=settings.reports_db,
                    validation_run_id=validation_run_id,
                ),
                root_ctx,
            )
            if not manifest_audit.complete:
                raise AppError(
                    code="validation_manifest_closure_incomplete",
                    message="Fixed-cohort ingest did not close every admitted report",
                    retryable=False,
                    context={
                        "validation_run_id": str(validation_run_id),
                        "incomplete_entity_count": len(
                            manifest_audit.incomplete_entity_ids
                        ),
                        "duplicate_current_entity_count": len(
                            manifest_audit.duplicate_current_entity_ids
                        ),
                        "missing_cohort_report_count": len(
                            manifest_audit.missing_cohort_report_ids
                        ),
                        "overlapping_current_report_count": len(
                            manifest_audit.overlapping_current_report_ids
                        ),
                        "duplicate_source_identity_count": len(
                            manifest_audit.duplicate_source_identity_ids
                        ),
                        "multiple_wordpress_post_report_count": len(
                            manifest_audit.multiple_wordpress_post_report_ids
                        ),
                        "totals_reconciled": manifest_audit.totals_reconciled,
                    },
                )
            reliability_artifact = build_validation_reliability_artifact(
                ValidationReliabilityBuildRequest(
                    schema_version="1.0",
                    reports_db_path=settings.reports_db,
                    usage_db_path=settings.usage_db_path,
                    validation_run_id=validation_run_id,
                ),
                root_ctx,
            )
            reliability_write = write_validation_reliability_artifact(
                ValidationReliabilityWriteRequest(
                    schema_version="1.0",
                    artifact_path=validation_reliability_artifact_path(
                        output_dir=settings.output_dir,
                        validation_run_id=str(validation_run_id),
                    ),
                    artifact=reliability_artifact,
                ),
                root_ctx,
            )
            logger.info(
                log_event(
                    root_ctx,
                    role="orchestrator",
                    event="ingest_validation_reliability_retained",
                    module=logger.name,
                    fields={
                        "validation_run_id": str(validation_run_id),
                        "artifact_path": reliability_write.artifact_path,
                        "artifact_hash": reliability_write.artifact_hash,
                    },
                )
            )
        processed = sum(result.processed for result in results)
        had_errors = any(result.had_error for result in results)

        logger.info(
            log_event(
                root_ctx,
                role="orchestrator",
                event="ingest_complete",
                module=logger.name,
                fields={"processed": processed},
            )
        )
        deps.vector_store_retention_cleanup(settings, root_ctx)
        _update_ingest_cursor(
            settings,
            processed=processed,
            had_errors=had_errors,
            attempt_limit=resolved_attempt_limit,
            root_ctx=root_ctx,
        )
        return outcomes
    except Exception as exc:
        record_workflow_failure(
            state_db=settings.state_db,
            workflow="ingest",
            stage="ingest_batch",
            operation="run_ingest",
            error=exc,
            ctx=root_ctx,
            input_checksum=remediation_input_checksum(
                {
                    "folder_id": folder_id or settings.gdrive_folder_id,
                    "attempt_limit": resolved_attempt_limit,
                    "legacy_limit_used": limit is not None,
                    "force_report_cards": force_report_cards,
                    "rescan": rescan,
                }
            ),
            source_id=folder_id or settings.gdrive_folder_id,
        )
        raise
    finally:
        _finalize_usage_projection(settings, root_ctx)
        finalize_ingest_run(
            lock_ctx=lock_ctx,
            lock_info=lock_info,
        )
