from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Callable, Iterable, List, Optional

from src.contracts.candidate_extraction import (
    CandidateExtractOutcome,
    CandidateExtractRequest,
)
from src.contracts.drive import DriveDownloadRequest, DriveFile, DriveListRequest
from src.contracts.files import (
    FileExistsRequest,
    FileHashRequest,
    ReadBytesRequest,
    WriteBytesRequest,
)
from src.contracts.ingest import IngestSettings
from src.contracts.pdf_utils import PdfEofCheckRequest
from src.contracts.remediation import RemediationArtifactReference
from src.contracts.run_context import RunContext
from src.contracts.semantic_ids import ReportId
from src.generators.candidate_extraction_generator import generate_candidate_pack
from src.orchestrators.remediation_orchestrator import (
    record_workflow_failure,
    remediation_input_checksum,
)
from src.orchestrators.retry_orchestrator import run_step_with_default_policy
from src.services.drive_service import download_pdf, list_pdfs
from src.services.file_service import (
    file_exists,
    file_md5,
    path_redirect_reason,
    read_bytes,
    write_bytes,
)
from src.services.pdf_service import check_pdf_eof
from src.utils.errors import AppError
from src.utils.logging import child_context, log_event, new_run_context
from src.utils.path_utils import (
    WINDOWS_COMPONENT_BUDGET,
    WINDOWS_PATH_BUDGET,
    bounded_artifact_filename,
    is_windows_reserved_component,
    safe_path_segment,
    safe_pdf_name,
    windows_path_units,
)
from src.utils.slugify import slugify

logger = logging.getLogger("market_lense.candidate_extraction_orchestrator")

_ATOMIC_TEMP_NAME = ".0000000000000000.0000000000000000"
_CACHE_IDENTITY_LENGTH = 12


@dataclass(frozen=True)
class CandidateExtractionDependencies:
    list_pdfs: Callable[[DriveListRequest, RunContext], Iterable[DriveFile]]
    download_pdf: Callable[[DriveDownloadRequest, RunContext], Any]
    file_exists: Callable[[FileExistsRequest, RunContext], Any]
    file_md5: Callable[[FileHashRequest, RunContext], Any]
    read_bytes: Callable[[ReadBytesRequest, RunContext], Any]
    write_bytes: Callable[[WriteBytesRequest, RunContext], Any]
    write_bytes_no_replace: Callable[[WriteBytesRequest, RunContext], Any]
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
            read_bytes=read_bytes,
            write_bytes=write_bytes,
            write_bytes_no_replace=_write_bytes_no_replace,
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


def _write_bytes_no_replace(request: WriteBytesRequest, ctx: RunContext) -> Any:
    return write_bytes(request, ctx, reject_conflicting_existing=True)


def _candidate_cache_path_error(path: Path, *, reason: str) -> AppError:
    return AppError(
        code="candidate_cache_path_invalid",
        message=(
            "Candidate PDF cache path cannot fit the supported Windows path policy"
        ),
        retryable=False,
        context={
            "path": str(path),
            "reason": reason,
            "windows_path_budget": WINDOWS_PATH_BUDGET,
            "windows_component_budget": WINDOWS_COMPONENT_BUDGET,
            "next_action": "Set a shorter writable candidate cache_dir",
        },
    )


def _candidate_cache_conflict(
    path: Path, *, cause: Exception | None = None
) -> AppError:
    return AppError(
        code="candidate_cache_conflict",
        message="Refusing to replace a conflicting source-associated candidate PDF",
        cause=cause,
        retryable=False,
        context={
            "path": str(path),
            "next_action": "Choose a new cache root or remove the conflicting artifact",
        },
    )


def _candidate_source_md5_mismatch(
    file: DriveFile, *, expected_md5: str, actual_md5: str
) -> AppError:
    return AppError(
        code="candidate_source_md5_mismatch",
        message=("Downloaded candidate PDF does not match the MD5 supplied by Drive"),
        retryable=False,
        context={
            "file_id": file.file_id,
            "expected_md5": expected_md5,
            "actual_md5": actual_md5,
            "next_action": (
                "Refresh Drive metadata and retry with the current source checksum"
            ),
        },
    )


def _resolved_candidate_cache_root(settings: IngestSettings) -> Path:
    try:
        root = Path(settings.cache_dir).expanduser().resolve()
    except (OSError, RuntimeError, TypeError, ValueError) as exc:
        raise _candidate_cache_path_error(
            Path(str(settings.cache_dir)), reason="cache_root_resolution_failed"
        ) from exc

    for component in root.parts:
        if component in {root.anchor, "", "."}:
            continue
        if (
            windows_path_units(component) > WINDOWS_COMPONENT_BUDGET
            or component != component.rstrip(" .")
            or is_windows_reserved_component(component)
        ):
            raise _candidate_cache_path_error(
                root, reason="cache_root_component_invalid"
            )
    temp_path_units = (
        windows_path_units(root) + 1 + windows_path_units(_ATOMIC_TEMP_NAME)
    )
    if temp_path_units > WINDOWS_PATH_BUDGET:
        raise _candidate_cache_path_error(
            root, reason="cache_root_atomic_temp_too_long"
        )
    return root


def _candidate_cache_filename(
    file: DriveFile, root: Path, *, content_md5: str | None = None
) -> str:
    raw_name = safe_pdf_name(file.name or f"{file.file_id}.pdf")
    safe_stem = safe_path_segment(Path(raw_name).stem.casefold(), fallback="candidate")
    file_identity = hashlib.sha256(file.file_id.encode("utf-8")).hexdigest()[
        :_CACHE_IDENTITY_LENGTH
    ]
    content_identity = ""
    source_md5 = content_md5 if content_md5 is not None else file.md5_checksum
    if source_md5:
        content_identity = hashlib.sha256(
            str(source_md5).strip().casefold().encode("utf-8")
        ).hexdigest()[:_CACHE_IDENTITY_LENGTH]
    identity_stem = f"{safe_stem}-{file_identity}"
    if content_identity:
        identity_stem = f"{identity_stem}-{content_identity}"

    available_units = min(
        WINDOWS_COMPONENT_BUDGET,
        WINDOWS_PATH_BUDGET - windows_path_units(root) - 1,
    )
    minimum_compacted_units = len("a-000000000000.pdf")
    if available_units < minimum_compacted_units:
        raise _candidate_cache_path_error(
            root, reason="cache_filename_budget_exhausted"
        )
    filename = bounded_artifact_filename(
        identity_stem,
        compact_stem=f"candidate-{file_identity}",
        extension=".pdf",
        max_length=available_units,
    )
    if windows_path_units(filename) > available_units or is_windows_reserved_component(
        filename
    ):
        raise _candidate_cache_path_error(
            root / filename, reason="cache_filename_budget_exhausted"
        )
    return filename


def _candidate_cache_paths(
    file: DriveFile,
    settings: IngestSettings,
    *,
    content_md5: str | None = None,
) -> tuple[Path, Path | None]:
    root = _resolved_candidate_cache_root(settings)
    filename = _candidate_cache_filename(file, root, content_md5=content_md5)
    canonical_path = root / filename
    if windows_path_units(canonical_path) > WINDOWS_PATH_BUDGET:
        raise _candidate_cache_path_error(canonical_path, reason="cache_path_too_long")

    legacy_candidate_path = root / safe_pdf_name(file.name or f"{file.file_id}.pdf")
    if (
        windows_path_units(legacy_candidate_path) > WINDOWS_PATH_BUDGET
        or windows_path_units(legacy_candidate_path.name) > WINDOWS_COMPONENT_BUDGET
        or is_windows_reserved_component(legacy_candidate_path.name)
    ):
        return canonical_path, None
    return canonical_path, legacy_candidate_path


def _validate_candidate_cache_path(path: Path, settings: IngestSettings) -> None:
    redirect_reason = path_redirect_reason(
        path,
        allowed_root=Path(settings.cache_dir).expanduser(),
    )
    if redirect_reason is not None:
        raise _candidate_cache_path_error(path, reason=redirect_reason)


def _download_if_needed(
    file: DriveFile,
    settings: IngestSettings,
    ctx: RunContext,
    dependencies: CandidateExtractionDependencies,
) -> tuple[str, Optional[str]]:
    cache_path_obj, legacy_path_obj = _candidate_cache_paths(file, settings)
    _validate_candidate_cache_path(cache_path_obj, settings)
    if legacy_path_obj is not None:
        _validate_candidate_cache_path(legacy_path_obj, settings)
    cache_path = str(cache_path_obj)
    md5 = None
    canonical_exists = False
    if file.md5_checksum:
        exists_resp = dependencies.file_exists(
            FileExistsRequest(schema_version="1.0", path=cache_path), ctx
        )
        canonical_exists = bool(exists_resp.exists)
    if canonical_exists and file.md5_checksum:
        try:
            md5_resp = dependencies.file_md5(
                FileHashRequest(schema_version="1.0", path=cache_path), ctx
            )
        except AppError as exc:
            if exc.code == "file_not_found":
                md5_resp = None
            else:
                raise
        if md5_resp is None:
            canonical_exists = False
        elif md5_resp.md5.casefold() == file.md5_checksum.casefold():
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
        else:
            raise _candidate_cache_conflict(
                cache_path_obj,
                cause=ValueError("existing candidate cache md5 does not match source"),
            )

    if not canonical_exists and file.md5_checksum and legacy_path_obj is not None:
        legacy_path = str(legacy_path_obj)
        legacy_exists = dependencies.file_exists(
            FileExistsRequest(schema_version="1.0", path=legacy_path), ctx
        )
        if legacy_exists.exists:
            legacy_md5 = dependencies.file_md5(
                FileHashRequest(schema_version="1.0", path=legacy_path), ctx
            )
            if legacy_md5.md5.casefold() == file.md5_checksum.casefold():
                legacy_content = dependencies.read_bytes(
                    ReadBytesRequest(schema_version="1.0", path=legacy_path), ctx
                ).content
                if (
                    hashlib.md5(legacy_content).hexdigest().casefold()
                    == file.md5_checksum.casefold()
                ):
                    try:
                        dependencies.write_bytes_no_replace(
                            WriteBytesRequest(
                                schema_version="1.0",
                                path=cache_path,
                                content=legacy_content,
                            ),
                            ctx,
                        )
                    except AppError as exc:
                        if exc.code != "file_write_conflict":
                            raise
                        raise _candidate_cache_conflict(
                            cache_path_obj, cause=exc
                        ) from exc
                    logger.info(
                        log_event(
                            ctx,
                            role="orchestrator",
                            event="pdf_cache_legacy_promoted",
                            module=logger.name,
                            fields={
                                "file_id": file.file_id,
                                "path": cache_path,
                                "legacy_path": legacy_path,
                                "md5": file.md5_checksum,
                            },
                        )
                    )
                    return cache_path, file.md5_checksum

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
        schema_version="1.0",
        file=file,
        service_account_path=settings.google_sa_path,
        auth_mode=settings.drive_auth_mode,
        oauth_client_path=settings.google_oauth_client_path,
        oauth_token_path=settings.google_oauth_token_path,
    )
    dl_resp = _run_step_with_retry(
        "download_pdf",
        ctx,
        lambda: dependencies.download_pdf(dl_req, ctx),
        dependencies,
    )
    downloaded_md5 = hashlib.md5(dl_resp.content).hexdigest()
    expected_md5 = str(file.md5_checksum or "").strip().casefold()
    if expected_md5 and downloaded_md5.casefold() != expected_md5:
        raise _candidate_source_md5_mismatch(
            file,
            expected_md5=expected_md5,
            actual_md5=downloaded_md5,
        )
    if not expected_md5:
        cache_path_obj, _ = _candidate_cache_paths(
            file, settings, content_md5=downloaded_md5
        )
        cache_path = str(cache_path_obj)
    try:
        dependencies.write_bytes_no_replace(
            WriteBytesRequest(
                schema_version="1.0", path=cache_path, content=dl_resp.content
            ),
            ctx,
        )
    except AppError as exc:
        if exc.code == "file_write_conflict":
            raise _candidate_cache_conflict(cache_path_obj, cause=exc) from exc
        raise
    md5 = downloaded_md5
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


def _record_candidate_failure(
    *,
    settings: IngestSettings,
    ctx: RunContext,
    error: Exception,
    report_id: str,
    source_id: str,
    pdf_path: str = "",
    input_checksum: str = "",
) -> None:
    artifacts = (
        [
            RemediationArtifactReference(
                schema_version="1.0",
                name="candidate_pdf",
                reference=pdf_path,
            )
        ]
        if pdf_path
        else []
    )
    record_workflow_failure(
        state_db=settings.state_db,
        workflow="candidate_extraction",
        stage="candidate_pack",
        operation="generate_candidate_pack",
        error=error,
        ctx=ctx,
        input_checksum=input_checksum
        or remediation_input_checksum(
            {"report_id": report_id, "source_id": source_id, "pdf_path": pdf_path}
        ),
        report_id=report_id,
        source_id=source_id,
        reusable_artifacts=artifacts,
    )


def _run_candidate_extraction(
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
            error = AppError(
                code="candidate_source_missing",
                message="Candidate extraction source PDF was not found",
                retryable=False,
                context={"report_id": report_id or name},
            )
            _record_candidate_failure(
                settings=settings,
                ctx=file_ctx,
                error=error,
                report_id=report_id or name,
                source_id=pdf_path,
                pdf_path=pdf_path,
            )
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
                    report_id=ReportId(report_id or name),
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
                    report_id=ReportId(resolved_report_id),
                    pdf_path=pdf_path,
                    output_dir=settings.output_dir,
                    report_name=name,
                ),
                file_ctx,
            )
            outcomes.append(outcome)
        except Exception as exc:
            _record_candidate_failure(
                settings=settings,
                ctx=file_ctx,
                error=exc,
                report_id=resolved_report_id,
                source_id=pdf_path,
                pdf_path=pdf_path,
                input_checksum=md5_resp.md5,
            )
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
                    report_id=ReportId(resolved_report_id),
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
        auth_mode=settings.drive_auth_mode,
        oauth_client_path=settings.google_oauth_client_path,
        oauth_token_path=settings.google_oauth_token_path,
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
        cache_path = ""
        try:
            cache_path, _ = _download_if_needed(file, settings, file_ctx, deps)
            report_name = _resolve_report_name(file, cache_path)
            outcome = deps.generate_candidate_pack(
                CandidateExtractRequest(
                    schema_version="1.0",
                    report_id=ReportId(file.file_id),
                    pdf_path=cache_path,
                    output_dir=settings.output_dir,
                    report_name=report_name,
                ),
                file_ctx,
            )
            outcomes.append(outcome)
            processed += 1
        except Exception as exc:
            _record_candidate_failure(
                settings=settings,
                ctx=file_ctx,
                error=exc,
                report_id=file.file_id,
                source_id=file.file_id,
                pdf_path=cache_path,
                input_checksum=file.md5_checksum or "",
            )
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
                    report_id=ReportId(file.file_id),
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
    """Extract candidates while retaining unexpected batch-level failures."""

    root_ctx = ctx or new_run_context()
    try:
        return _run_candidate_extraction(
            settings,
            folder_id=folder_id,
            limit=limit,
            file_id=file_id,
            pdf_path=pdf_path,
            report_id=report_id,
            ctx=root_ctx,
            dependencies=dependencies,
        )
    except Exception as exc:
        _record_candidate_failure(
            settings=settings,
            ctx=root_ctx,
            error=exc,
            report_id=report_id or file_id or "",
            source_id=pdf_path or folder_id or settings.gdrive_folder_id,
            pdf_path=pdf_path or "",
        )
        raise
