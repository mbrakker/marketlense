from __future__ import annotations

import json
import logging
import mimetypes
import re
import time
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserDownloadIdentityFieldUpsertRequest,
    BrowserDownloadIdentityFieldUpsertResponse,
    DownloadTerminalEvidence,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    BrowserRoutePlaybookPromotionResponse,
    FailedAcquisitionForensicsArtifact,
    FailedAcquisitionForensicsPack,
    PublisherDownloadRouteMemory,
    ReportDownloadRoutePlanRequest,
    ReportDownloadRoutePlanStep,
    ReportDownloadDriveUpload,
    ReportDownloadOrchestratorRequest,
    ReportDownloadOrchestratorResult,
)
from src.contracts.drive import (
    DriveFile,
    DriveFolderFileListRequest,
    DriveFolderFileListResponse,
    DriveUploadLocalFileRequest,
    DriveUploadLocalFileResponse,
)
from src.contracts.files import FileHashRequest, FileHashResponse
from src.contracts.files import (
    ReadBytesRequest,
    ReadBytesResponse,
    WriteBytesRequest,
    WriteBytesResponse,
)
from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.report_store import (
    PublisherDownloadRouteGetRequest,
    PublisherDownloadRouteRecordRequest,
    PublisherDownloadRouteResponse,
    ReportDownloadDriveFolderLookupRequest,
    ReportDownloadDriveFolderLookupResponse,
    ReportSourceRecordRequest,
    ReportSourceRecordResponse,
    ReportValueScoreRecordRequest,
    ReportValueScoreRequest,
    ReportValueScoreResponse,
)
from src.contracts.run_context import RunContext
from src.orchestrators.retry_orchestrator import (
    RetryPolicy,
    is_retryable_app_error,
    run_with_retry,
)
from src.orchestrators._report_download_orchestrator.route_planner import (
    plan_report_download_routes,
)
from src.generators.report_value_generator import score_report_value
from src.services.browser_report_download_service import (
    download_report_with_browser_use,
    promote_validated_browser_route_result_to_playbook,
)
from src.services import idempotency_service
from src.services.file_service import file_md5, read_bytes, write_bytes
from src.services._browser_report_download.request import resolve_download_dir_path
from src.services.drive_service import list_files_in_folder, upload_local_file
from src.services.report_store_service import (
    get_report_download_drive_folder,
    get_publisher_download_route,
    record_publisher_download_route,
    record_report_value_score,
    record_report_source,
)
from src.services.config_service import upsert_browser_download_identity_fields
from src.utils.drive_utils import extract_drive_folder_id
from src.utils.logging import log_event
from src.utils.errors import AppError
from src.utils.cache_utils import sha256_json
from src.utils.coercion import coerce_int
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.report_download_orchestrator")
_REPORT_DOWNLOAD_ROUTE_RECORD_SCOPE = "report_download_orchestrator.route_record"
_REPORT_DOWNLOAD_SOURCE_RECORD_SCOPE = "report_download_orchestrator.source_record"
_REPORT_DOWNLOAD_DRIVE_UPLOAD_SCOPE = "report_download_orchestrator.drive_upload"
_REPORT_DOWNLOAD_IDENTITY_UPDATE_SCOPE = "report_download_orchestrator.identity_update"
_MAX_FORENSICS_CONTEXT_CHARS = 500
_ROUTE_PLAYBOOK_PROMOTION_MODES = {"disabled", "dry_run", "write"}
_ROUTE_PLAYBOOK_SUCCESS_OUTCOMES = {"downloaded", "email_requested", "captured"}
_ROUTE_PLAYBOOK_VERIFIED_STATUSES = {"verified", "recovered"}
_NON_REPORT_URL_MARKERS = {
    "blog",
    "news",
    "press",
    "case-study",
    "case_study",
    "webinar",
    "podcast",
    "faq",
    "support",
    "contact",
}
_ASSET_URL_MARKERS = {
    "logo",
    "image",
    "images",
    "video",
    "webp",
    "jpg",
    "jpeg",
    "png",
    "svg",
}
_MARKETING_URL_MARKERS = {
    "demo",
    "pricing",
    "contact-sales",
    "contact_sales",
    "book-a-demo",
    "book_demo",
    "request-pricing",
    "signup",
    "sign-up",
}
_NON_REPORT_TITLE_MARKERS = {
    "case study",
    "webinar",
    "podcast",
    "press release",
    "support",
    "help center",
    "customer story",
}
_REPORT_TITLE_MARKERS = {
    "report",
    "research",
    "study",
    "survey",
    "insight",
    "analysis",
    "outlook",
    "whitepaper",
    "white paper",
    "guide",
    "playbook",
    "trend",
    "ebook",
}
_REPORT_RESOURCE_URL_MARKERS = {
    "resource",
    "resources",
    "whitepaper",
    "whitepapers",
    "guide",
    "guides",
    "playbook",
    "playbooks",
    "ebook",
    "ebooks",
}
_REPORT_SOURCE_PAGE_MARKERS = {
    "insights",
    "reports",
    "research",
    "resources",
    "publications",
}
_MIXED_CONTENT_HUB_SEGMENTS = {
    "insight",
    "insights",
    "report",
    "reports",
    "research",
    "resource",
    "resources",
    "publication",
    "publications",
    "library",
    "blog",
    "news",
}
_REPORT_DETAIL_TITLE_MARKERS = {
    "benchmark",
    "ebook",
    "e-book",
    "guide",
    "market",
    "outlook",
    "playbook",
    "prediction",
    "predictions",
    "report",
    "research",
    "study",
    "survey",
    "trend",
    "trends",
    "whitepaper",
    "white paper",
}


@dataclass(frozen=True)
class ReportDownloadDependencies:
    download_report_with_browser_use: Callable[
        [BrowserReportDownloadRequest, RunContext],
        BrowserReportDownloadResult,
    ]
    get_publisher_download_route: Callable[
        [PublisherDownloadRouteGetRequest, RunContext],
        Optional[PublisherDownloadRouteResponse],
    ]
    record_publisher_download_route: Callable[
        [PublisherDownloadRouteRecordRequest, RunContext],
        None,
    ]
    file_md5: Callable[[FileHashRequest, RunContext], FileHashResponse]
    record_report_source: Callable[
        [ReportSourceRecordRequest, RunContext],
        ReportSourceRecordResponse,
    ]
    upsert_browser_download_identity_fields: Callable[
        [BrowserDownloadIdentityFieldUpsertRequest, RunContext],
        BrowserDownloadIdentityFieldUpsertResponse,
    ]
    sleep_fn: Callable[[float], None]
    promote_validated_browser_route_result_to_playbook: Callable[
        ..., BrowserRoutePlaybookPromotionResponse
    ] = promote_validated_browser_route_result_to_playbook
    score_report_value: Callable[
        [ReportValueScoreRequest, RunContext],
        ReportValueScoreResponse,
    ] = score_report_value
    record_report_value_score: Callable[
        [ReportValueScoreRecordRequest, RunContext],
        None,
    ] = record_report_value_score
    read_bytes: Callable[[ReadBytesRequest, RunContext], ReadBytesResponse] = read_bytes
    write_bytes: Callable[[WriteBytesRequest, RunContext], WriteBytesResponse] = (
        write_bytes
    )
    get_report_download_drive_folder: Callable[
        [ReportDownloadDriveFolderLookupRequest, RunContext],
        Optional[ReportDownloadDriveFolderLookupResponse],
    ] = get_report_download_drive_folder
    list_files_in_folder: Callable[
        [DriveFolderFileListRequest, RunContext],
        DriveFolderFileListResponse,
    ] = list_files_in_folder
    upload_local_file: Callable[
        [DriveUploadLocalFileRequest, RunContext],
        DriveUploadLocalFileResponse,
    ] = upload_local_file

    @classmethod
    def default(cls) -> "ReportDownloadDependencies":
        return cls(
            download_report_with_browser_use=download_report_with_browser_use,
            get_publisher_download_route=get_publisher_download_route,
            record_publisher_download_route=record_publisher_download_route,
            file_md5=file_md5,
            record_report_source=record_report_source,
            score_report_value=score_report_value,
            record_report_value_score=record_report_value_score,
            read_bytes=read_bytes,
            write_bytes=write_bytes,
            get_report_download_drive_folder=get_report_download_drive_folder,
            list_files_in_folder=list_files_in_folder,
            upload_local_file=upload_local_file,
            upsert_browser_download_identity_fields=upsert_browser_download_identity_fields,
            sleep_fn=time.sleep,
        )


def _lookup_idempotency_record(
    *,
    db_path: str,
    scope: str,
    idempotency_key: str,
    input_checksum: str,
    ctx: RunContext,
):
    lookup = idempotency_service.get_outcome(
        OrchestratorIdempotencyGetRequest(
            schema_version="1.0",
            db_path=db_path,
            scope=scope,
            idempotency_key=idempotency_key,
            input_checksum=input_checksum,
        ),
        ctx,
    )
    return lookup.record if lookup.found else None


def _record_idempotency_outcome(
    *,
    db_path: str,
    scope: str,
    idempotency_key: str,
    input_checksum: str,
    outcome_payload: dict[str, object],
    artifact_references: dict[str, object],
    ctx: RunContext,
) -> None:
    idempotency_service.record_outcome(
        OrchestratorIdempotencyRecordRequest(
            schema_version="1.0",
            db_path=db_path,
            scope=scope,
            idempotency_key=idempotency_key,
            input_checksum=input_checksum,
            outcome_payload=outcome_payload,
            artifact_references=artifact_references,
        ),
        ctx,
    )


def _idempotency_key_with_checksum(*parts: str, checksum: str) -> str:
    tokens = [str(part or "").strip() for part in parts if str(part or "").strip()]
    tokens.append(checksum)
    return ":".join(tokens)


def _serialize_terminal_evidence_for_idempotency(
    terminal_evidence: DownloadTerminalEvidence | None,
) -> dict[str, object] | None:
    if terminal_evidence is None:
        return None
    return {
        "schema_version": terminal_evidence.schema_version,
        "final_page_url": terminal_evidence.final_page_url,
        "final_page_title": terminal_evidence.final_page_title,
        "terminal_text_excerpt": terminal_evidence.terminal_text_excerpt,
        "artifact_url": terminal_evidence.artifact_url,
        "artifact_kind": terminal_evidence.artifact_kind,
        "artifact_validation_status": terminal_evidence.artifact_validation_status,
        "artifact_validation_detail": terminal_evidence.artifact_validation_detail,
        "confirmation_signal_count": terminal_evidence.confirmation_signal_count,
        "traversed_page_urls": list(terminal_evidence.traversed_page_urls or []),
        "network_events": [
            asdict(event) for event in (terminal_evidence.network_events or [])
        ],
    }


def _route_record_checksum(
    request: PublisherDownloadRouteRecordRequest,
) -> str:
    payload = {
        "schema_version": "1.0",
        "normalized_url": request.normalized_url,
        "source_url": request.source_url,
        "route_kind": request.route_kind,
        "route_summary": request.route_summary,
        "outcome": request.outcome,
        "route_family": request.route_family,
        "route_status": request.route_status,
        "resolved_target_url": request.resolved_target_url,
        "route_steps": [asdict(step) for step in request.route_steps],
        "confirmation_evidence": (
            asdict(request.confirmation_evidence)
            if request.confirmation_evidence is not None
            else None
        ),
        "terminal_evidence": _serialize_terminal_evidence_for_idempotency(
            request.terminal_evidence
        ),
        "browser_had_structured_result": bool(request.browser_had_structured_result),
        "used_candidate_pdf_url": bool(request.used_candidate_pdf_url),
        "used_candidate_source_page": bool(request.used_candidate_source_page),
        "candidate_pdf_url": request.candidate_pdf_url,
        "candidate_source_page_urls": list(request.candidate_source_page_urls or []),
        "candidate_discovery_provenances": list(
            request.candidate_discovery_provenances or []
        ),
        "publisher_discovery_route_kind": request.publisher_discovery_route_kind,
        "publisher_recommended_discovery_route_kind": (
            request.publisher_recommended_discovery_route_kind
        ),
        "blocked_reason": request.blocked_reason,
        "blocked_reason_detail": request.blocked_reason_detail,
        "last_final_page_url": request.last_final_page_url,
        "onsite_capture_format": request.onsite_capture_format,
        "onsite_page_count": request.onsite_page_count,
        "onsite_completeness_status": request.onsite_completeness_status,
    }
    return sha256_json(payload)


def _identity_update_checksum(
    request: BrowserDownloadIdentityFieldUpsertRequest,
) -> str:
    encountered_fields = sorted(
        {
            str(field or "").strip()
            for field in (request.encountered_form_fields or [])
            if str(field or "").strip()
        }
    )
    return sha256_json(
        {
            "schema_version": "1.0",
            "path": request.path,
            "encountered_form_fields": encountered_fields,
        }
    )


def _restore_identity_update_response(
    payload: dict[str, object],
) -> BrowserDownloadIdentityFieldUpsertResponse:
    raw_added_field_keys = payload.get("added_field_keys")
    added_field_keys = (
        raw_added_field_keys if isinstance(raw_added_field_keys, list) else []
    )
    return BrowserDownloadIdentityFieldUpsertResponse(
        schema_version=str(payload.get("schema_version") or "1.0"),
        path=str(payload.get("path") or ""),
        added_field_keys=[
            str(item) for item in added_field_keys if str(item or "").strip()
        ],
        total_fields=coerce_int(payload.get("total_fields"), 0),
    )


def _identity_update_response_payload(
    response: object,
) -> dict[str, object]:
    added_field_keys = getattr(response, "added_field_keys", [])
    return {
        "schema_version": str(getattr(response, "schema_version", "1.0") or "1.0"),
        "path": str(getattr(response, "path", "") or ""),
        "added_field_keys": [
            str(item)
            for item in list(added_field_keys or [])
            if str(item or "").strip()
        ],
        "total_fields": coerce_int(getattr(response, "total_fields", 0), 0),
    }


def _evaluate_route_playbook_promotion(
    *,
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
    route_record_reused: bool,
) -> None:
    mode = str(
        getattr(request.settings, "route_playbook_promotion_mode", "disabled")
        or "disabled"
    ).strip()
    if mode not in _ROUTE_PLAYBOOK_PROMOTION_MODES:
        mode = "disabled"
    fields: dict[str, object] = {
        "promotion_mode": mode,
        "route_playbook_dir": request.settings.route_playbook_dir,
        "normalized_url": result.normalized_url,
        "route_family": result.route_family,
        "route_kind": result.route_kind,
        "route_status": result.route_status,
        "outcome": result.outcome,
        "route_step_count": len(result.route_steps),
        "browser_had_structured_result": result.browser_had_structured_result,
    }
    skip_reason = _route_playbook_promotion_skip_reason(
        mode=mode,
        result=result,
        route_record_reused=route_record_reused,
    )
    if skip_reason:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_route_playbook_promotion_evaluated",
                module=logger.name,
                fields={**fields, "skip_reason": skip_reason},
            )
        )
        return
    try:
        response = dependencies.promote_validated_browser_route_result_to_playbook(
            playbook_dir=request.settings.route_playbook_dir,
            result=result,
            ctx=ctx,
            observed_at=_utc_now_iso(),
            write_file=mode == "write",
        )
    except AppError as exc:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_route_playbook_promotion_evaluated",
                module=logger.name,
                fields={
                    **fields,
                    "skip_reason": "promotion_app_error",
                    "error_code": exc.code,
                    "error_retryable": exc.retryable,
                },
            )
        )
        return
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_route_playbook_promotion_evaluated",
            module=logger.name,
            fields={
                **fields,
                "playbook_id": response.playbook_id,
                "playbook_path": response.path,
                "playbook_version": response.version,
                "promotion_status": response.status,
                "review_diff_line_count": len(response.review_diff.splitlines()),
            },
        )
    )


def _route_playbook_promotion_skip_reason(
    *,
    mode: str,
    result: BrowserReportDownloadResult,
    route_record_reused: bool,
) -> str:
    if mode == "disabled":
        return "promotion_disabled"
    if route_record_reused:
        return "route_record_idempotency_reused"
    if not str(result.route_family or "").startswith("browser_"):
        return "non_browser_route_family"
    if result.route_status not in _ROUTE_PLAYBOOK_VERIFIED_STATUSES:
        return "unverified_route_status"
    if result.outcome not in _ROUTE_PLAYBOOK_SUCCESS_OUTCOMES:
        return "unsuccessful_route_outcome"
    if not result.browser_had_structured_result:
        return "insufficient_structured_browser_evidence"
    if not result.route_steps:
        return "insufficient_route_steps"
    if not str(result.route_summary or "").strip():
        return "missing_route_summary"
    return ""


def _failure_error_class(exc: Exception) -> str:
    if not isinstance(exc, AppError):
        return "unexpected_exception"
    if exc.retryable:
        return "transient_app_error"
    return "permanent_app_error"


def _forensics_safe_token(value: str) -> str:
    cleaned = "".join(
        character if character.isalnum() else "_"
        for character in str(value or "").strip().lower()
    ).strip("_")
    return cleaned or "unknown"


def _bounded_forensics_token(value: str, *, max_chars: int) -> str:
    token = _forensics_safe_token(value)
    return token[:max_chars].rstrip("_") or token


def _truncated_context_value(value: object) -> object:
    if isinstance(value, dict):
        return {str(key): _truncated_context_value(item) for key, item in value.items()}
    if isinstance(value, list):
        return [_truncated_context_value(item) for item in value[:25]]
    if isinstance(value, str):
        return (
            value
            if len(value) <= _MAX_FORENSICS_CONTEXT_CHARS
            else value[: _MAX_FORENSICS_CONTEXT_CHARS - 3] + "..."
        )
    if isinstance(value, (int, float, bool)) or value is None:
        return value
    return str(value)


def _coerce_network_events(
    value: object,
):
    from src.contracts.browser_download import BrowserDownloadNetworkEvent

    events: list[BrowserDownloadNetworkEvent] = []
    if not isinstance(value, list):
        return events
    for item in value:
        if not isinstance(item, dict):
            continue
        url = str(item.get("url") or "").strip()
        if not url:
            continue
        events.append(
            BrowserDownloadNetworkEvent(
                schema_version=str(item.get("schema_version") or "1.0"),
                url=url,
                initiator_type=str(item.get("initiator_type") or "other"),
                signal_kind=str(item.get("signal_kind") or "other"),
            )
        )
    return events


def _terminal_evidence_from_error_context(
    *,
    exc: Exception,
    request: ReportDownloadOrchestratorRequest,
    planned_step: ReportDownloadRoutePlanStep,
) -> DownloadTerminalEvidence | None:
    if not isinstance(exc, AppError):
        return None
    context = dict(exc.context or {})
    final_page_url = str(
        context.get("final_page_url")
        or context.get("final_url")
        or planned_step.attempt_url
        or request.url
    ).strip()
    if not final_page_url and not context:
        return None
    blocked_reason = str(context.get("blocked_reason") or "").strip()
    blocked_reason_detail = str(context.get("blocked_reason_detail") or "").strip()
    terminal_text_excerpt = str(context.get("terminal_text_excerpt") or "").strip()
    artifact_validation_status = "blocked" if blocked_reason else "none"
    artifact_validation_detail = (
        blocked_reason_detail or terminal_text_excerpt or exc.code
    )
    traversed_page_urls: list[str] = []
    for raw_value in (
        planned_step.attempt_url,
        context.get("execution_url"),
        final_page_url,
    ):
        token = str(raw_value or "").strip()
        if token and token not in traversed_page_urls:
            traversed_page_urls.append(token)
    return DownloadTerminalEvidence(
        schema_version="1.0",
        final_page_url=final_page_url,
        final_page_title=str(context.get("final_page_title") or "").strip(),
        terminal_text_excerpt=terminal_text_excerpt,
        artifact_url=str(context.get("resolved_target_url") or final_page_url).strip(),
        artifact_kind=str(context.get("route_kind") or "none").strip() or "none",
        artifact_validation_status=artifact_validation_status,
        artifact_validation_detail=artifact_validation_detail,
        confirmation_signal_count=0,
        traversed_page_urls=traversed_page_urls,
        visited_url_timeline=list(traversed_page_urls),
        observed_document_urls=[],
        network_events=_coerce_network_events(context.get("network_events")),
        html_snapshot_path=str(context.get("html_snapshot_path") or "").strip(),
        screenshot_path=str(context.get("screenshot_path") or "").strip(),
        dom_snapshot_sha256=str(context.get("dom_snapshot_sha256") or "").strip(),
        evidence_labels=[
            planned_step.route_family,
            exc.code,
            blocked_reason or artifact_validation_status,
        ],
    )


def _failure_artifact_candidates(
    *,
    exc: Exception,
    terminal_evidence: DownloadTerminalEvidence | None,
) -> list[tuple[str, str]]:
    context = dict(exc.context or {}) if isinstance(exc, AppError) else {}
    candidates: list[tuple[str, str]] = []

    def add(label: str, raw_path: object) -> None:
        token = str(raw_path or "").strip()
        if not token:
            return
        marker = (label, str(Path(token)))
        if marker in seen:
            return
        seen.add(marker)
        candidates.append((label, token))

    seen: set[tuple[str, str]] = set()
    if terminal_evidence is not None:
        add("terminal_html_snapshot", terminal_evidence.html_snapshot_path)
        add("terminal_screenshot", terminal_evidence.screenshot_path)
    add("downloaded_artifact", context.get("downloaded_file_path"))
    add("onsite_capture", context.get("onsite_capture_path"))
    claimed_paths = context.get("claimed_artifact_paths")
    if isinstance(claimed_paths, list):
        for index, claimed_path in enumerate(claimed_paths):
            add(f"claimed_artifact_{index + 1}", claimed_path)
    return candidates


def _persist_forensics_artifact(
    *,
    artifact_label: str,
    source_path: str,
    forensics_dir: Path,
    artifact_policy: str,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> FailedAcquisitionForensicsArtifact:
    source = Path(source_path)
    if not source.exists() or not source.is_file():
        return FailedAcquisitionForensicsArtifact(
            schema_version="1.0",
            artifact_label=artifact_label,
            source_path=source_path,
            persisted_path=None,
            retention_action="missing",
            size_bytes=None,
            md5=None,
        )
    if artifact_policy == "metadata_only":
        return FailedAcquisitionForensicsArtifact(
            schema_version="1.0",
            artifact_label=artifact_label,
            source_path=source_path,
            persisted_path=None,
            retention_action="metadata_only",
            size_bytes=None,
            md5=None,
        )
    read_response = dependencies.read_bytes(
        ReadBytesRequest(schema_version="1.0", path=source_path),
        ctx,
    )
    target_name = f"{_forensics_safe_token(artifact_label)}__{source.name}"
    target_path = forensics_dir / target_name
    write_response = dependencies.write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=str(target_path),
            content=read_response.content,
            make_parents=True,
        ),
        ctx,
    )
    return FailedAcquisitionForensicsArtifact(
        schema_version="1.0",
        artifact_label=artifact_label,
        source_path=source_path,
        persisted_path=write_response.path,
        retention_action="copied",
        size_bytes=write_response.bytes_written,
        md5=write_response.md5,
    )


def _with_failure_forensics_context(
    exc: AppError,
    *,
    pack: FailedAcquisitionForensicsPack | None,
    terminal_evidence: DownloadTerminalEvidence | None,
) -> AppError:
    context = dict(exc.context or {})
    context["failure_error_class"] = _failure_error_class(exc)
    if terminal_evidence is not None:
        context["terminal_evidence"] = asdict(terminal_evidence)
        context["terminal_html_snapshot_path"] = terminal_evidence.html_snapshot_path
        context["terminal_screenshot_path"] = terminal_evidence.screenshot_path
    if pack is not None:
        context["failure_forensics_pack_path"] = pack.pack_path
        context["failure_forensics_artifact_policy"] = pack.artifact_policy
        context["failure_forensics_artifacts"] = [
            asdict(item) for item in pack.artifacts
        ]
    return AppError(
        code=exc.code,
        message=exc.message,
        cause=exc.cause,
        retryable=exc.retryable,
        severity=exc.severity,
        context=context,
    )


def _persist_failed_attempt_forensics_pack(
    *,
    request: ReportDownloadOrchestratorRequest,
    planned_step: ReportDownloadRoutePlanStep,
    exc: AppError,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> FailedAcquisitionForensicsPack | None:
    if not request.settings.failure_forensics_enabled:
        return None
    normalized_url = normalize_url(request.url)
    download_dir = resolve_download_dir_path(
        root_dir=request.settings.output_dir,
        normalized_url=normalized_url,
    )
    forensics_dir = download_dir.parent / f"{download_dir.name}__failure_forensics"
    artifact_policy = str(request.settings.failure_forensics_policy or "copy_artifacts")
    terminal_evidence = _terminal_evidence_from_error_context(
        exc=exc,
        request=request,
        planned_step=planned_step,
    )
    artifacts = [
        _persist_forensics_artifact(
            artifact_label=artifact_label,
            source_path=source_path,
            forensics_dir=forensics_dir,
            artifact_policy=artifact_policy,
            ctx=ctx,
            dependencies=dependencies,
        )
        for artifact_label, source_path in _failure_artifact_candidates(
            exc=exc,
            terminal_evidence=terminal_evidence,
        )
    ]
    pack_name = (
        f"failed_attempt__{_bounded_forensics_token(planned_step.step_name, max_chars=18)}__"
        f"{_bounded_forensics_token(exc.code, max_chars=28)}.json"
    )
    pack_path = str(forensics_dir / pack_name)
    pack = FailedAcquisitionForensicsPack(
        schema_version="1.0",
        pack_path=pack_path,
        artifact_policy=artifact_policy,
        normalized_url=normalized_url,
        source_url=request.url,
        attempt_url=str(planned_step.attempt_url or request.url).strip(),
        step_name=planned_step.step_name,
        route_family=planned_step.route_family,
        route_kind_hint=planned_step.route_kind_hint,
        route_hint=planned_step.route_hint,
        route_step_hints=list(planned_step.route_step_hints),
        error_code=exc.code,
        error_message=exc.message,
        error_class=_failure_error_class(exc),
        error_retryable=exc.retryable,
        error_severity=exc.severity,
        blocked_reason=str((exc.context or {}).get("blocked_reason") or "").strip()
        or None,
        blocked_reason_detail=str(
            (exc.context or {}).get("blocked_reason_detail") or ""
        ).strip()
        or None,
        terminal_evidence=terminal_evidence,
        artifacts=artifacts,
        failure_context={
            str(key): _truncated_context_value(value)
            for key, value in dict(exc.context or {}).items()
        },
    )
    dependencies.write_bytes(
        WriteBytesRequest(
            schema_version="1.0",
            path=pack_path,
            content=json.dumps(asdict(pack), indent=2, sort_keys=True).encode("utf-8"),
            make_parents=True,
        ),
        ctx,
    )
    return pack


def _restore_report_source_record(
    payload: dict[str, object],
) -> ReportSourceRecordResponse:
    return ReportSourceRecordResponse(
        schema_version=str(payload.get("schema_version") or "1.0"),
        record_id=coerce_int(payload.get("record_id"), 0),
        source_domain=str(payload.get("source_domain") or ""),
        report_name=str(payload.get("report_name") or ""),
        landing_page_url=str(payload.get("landing_page_url") or ""),
        downloaded_at_utc=str(payload.get("downloaded_at_utc") or ""),
        md5=str(payload.get("md5") or ""),
    )


def _payload_optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    token = str(value).strip()
    return token or None


def _restore_drive_file(payload: dict[str, object]) -> DriveFile:
    return DriveFile(
        schema_version=str(payload.get("schema_version") or "1.0"),
        file_id=str(payload.get("file_id") or ""),
        name=str(payload.get("name") or ""),
        modified_time=_payload_optional_str(payload, "modified_time"),
        md5_checksum=_payload_optional_str(payload, "md5_checksum"),
        mime_type=_payload_optional_str(payload, "mime_type"),
    )


def _restore_drive_upload(payload: dict[str, object]) -> ReportDownloadDriveUpload:
    drive_file_payload = payload.get("drive_file")
    drive_file = (
        _restore_drive_file(drive_file_payload)
        if isinstance(drive_file_payload, dict)
        else DriveFile(
            schema_version="1.0",
            file_id="",
            name="",
            modified_time=None,
            md5_checksum=None,
            mime_type=None,
        )
    )
    return ReportDownloadDriveUpload(
        schema_version=str(payload.get("schema_version") or "1.0"),
        local_path=str(payload.get("local_path") or ""),
        file_name=str(payload.get("file_name") or ""),
        mime_type=str(payload.get("mime_type") or ""),
        folder_id=str(payload.get("folder_id") or ""),
        status=str(payload.get("status") or ""),
        size=coerce_int(payload.get("size"), 0),
        md5=(str(payload.get("md5")) if payload.get("md5") is not None else None),
        drive_file=drive_file,
    )


def run_report_download(
    request: ReportDownloadOrchestratorRequest,
    *,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies | None = None,
) -> ReportDownloadOrchestratorResult:
    deps = dependencies or ReportDownloadDependencies.default()
    normalized_url = normalize_url(request.url)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_start",
            module=logger.name,
            fields={
                "url": request.url,
                "normalized_url": normalized_url,
                "reports_db": request.reports_db,
                "has_delivery_email": bool(request.delivery_email),
                "has_candidate_trace": request.candidate_trace is not None,
                "has_publisher_insights_url": bool(request.publisher_insights_url),
                "has_publisher_google_folder": bool(request.publisher_google_folder),
                "drive_upload_enabled": request.settings.drive_upload_enabled,
                "publisher_discovery_route_kind": request.publisher_discovery_route_kind
                or "",
                "publisher_recommended_discovery_route_kind": (
                    request.publisher_recommended_discovery_route_kind or ""
                ),
            },
        )
    )
    _assert_candidate_download_ready(
        request=request, normalized_url=normalized_url, ctx=ctx
    )
    remembered_route = deps.get_publisher_download_route(
        PublisherDownloadRouteGetRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            normalized_url=normalized_url,
            publisher_scope_url=_publisher_scope_url_for_request(request),
        ),
        ctx,
    )
    if remembered_route is None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_memory_miss",
                module=logger.name,
                fields={"normalized_url": normalized_url},
            )
        )
    else:
        memory_event = (
            "report_download_memory_hit"
            if remembered_route.exact_route_found
            else "report_download_publisher_policy_hit"
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event=memory_event,
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "exact_route_found": remembered_route.exact_route_found,
                    "route_kind": remembered_route.route_kind,
                    "outcome": remembered_route.outcome,
                    "publisher_scope_url": remembered_route.publisher_scope_url or "",
                    "publisher_route_policy_order": [
                        signal.route_family
                        for signal in remembered_route.publisher_route_policy
                    ],
                },
            )
        )

    policy = RetryPolicy(
        retries=request.settings.retry_retries,
        base_delay_seconds=request.settings.retry_base_delay_seconds,
        backoff_step_seconds=request.settings.retry_backoff_step_seconds,
        jitter_seconds=request.settings.retry_jitter_seconds,
    )

    plan = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url=normalized_url,
            remembered_route=_remembered_route_memory(remembered_route),
            candidate_trace=request.candidate_trace,
            publisher_discovery_route_kind=request.publisher_discovery_route_kind,
            publisher_recommended_discovery_route_kind=request.publisher_recommended_discovery_route_kind,
        ),
        ctx,
    )
    result: BrowserReportDownloadResult | None = None
    last_retryable_error: AppError | None = None
    for planned_step in plan.steps:
        try:
            result = _run_download_attempt(
                request=request,
                ctx=ctx,
                policy=policy,
                dependencies=deps,
                planned_step=planned_step,
            )
            break
        except AppError as exc:
            attempt_retryable = _is_download_attempt_retryable(
                exc=exc,
                planned_step=planned_step,
            )
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="report_download_step_failed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "step_name": planned_step.step_name,
                        "route_family": planned_step.route_family,
                        "attempt_url": planned_step.attempt_url or "",
                        "recovery_class": planned_step.recovery_class
                        or planned_step.route_family,
                        "recovery_decision": planned_step.recovery_decision,
                        "error_code": exc.code,
                        "error_class": _failure_error_class(exc),
                        "error_message": exc.message,
                        "attempt_retryable": attempt_retryable,
                        "fallback_on_retryable_error": planned_step.fallback_on_retryable_error,
                        "failure_forensics_pack_path": str(
                            (exc.context or {}).get("failure_forensics_pack_path") or ""
                        ),
                        "failure_forensics_artifact_policy": str(
                            (exc.context or {}).get("failure_forensics_artifact_policy")
                            or ""
                        ),
                        "terminal_html_snapshot_path": str(
                            (exc.context or {}).get("terminal_html_snapshot_path") or ""
                        ),
                        "terminal_screenshot_path": str(
                            (exc.context or {}).get("terminal_screenshot_path") or ""
                        ),
                        "blocked_reason": str(
                            (exc.context or {}).get("blocked_reason") or ""
                        ),
                    },
                )
            )
            if not attempt_retryable:
                raise
            last_retryable_error = exc
            if not planned_step.fallback_on_retryable_error:
                raise
    if result is None:
        if last_retryable_error is not None:
            raise last_retryable_error
        raise AppError(
            code="report_download_plan_exhausted",
            message="The report download route plan completed without a result",
            retryable=True,
            context={"normalized_url": normalized_url},
        )

    route_record_request = PublisherDownloadRouteRecordRequest(
        schema_version="1.0",
        db_path=request.reports_db,
        normalized_url=result.normalized_url,
        source_url=result.source_url,
        route_kind=result.route_kind,
        route_summary=result.route_summary,
        outcome=result.outcome,
        route_family=result.route_family,
        route_status=result.route_status,
        resolved_target_url=result.resolved_target_url,
        route_steps=result.route_steps,
        confirmation_evidence=result.confirmation_evidence,
        terminal_evidence=result.terminal_evidence,
        browser_had_structured_result=result.browser_had_structured_result,
        used_candidate_pdf_url=result.used_candidate_pdf_url,
        used_candidate_source_page=result.used_candidate_source_page,
        candidate_pdf_url=(
            request.candidate_trace.pdf_url if request.candidate_trace else None
        ),
        candidate_source_page_urls=(
            list(request.candidate_trace.source_page_urls)
            if request.candidate_trace is not None
            else []
        ),
        candidate_discovery_provenances=(
            list(request.candidate_trace.discovery_provenances)
            if request.candidate_trace is not None
            else []
        ),
        publisher_discovery_route_kind=request.publisher_discovery_route_kind,
        publisher_recommended_discovery_route_kind=request.publisher_recommended_discovery_route_kind,
        blocked_reason=result.blocked_reason,
        blocked_reason_detail=result.blocked_reason_detail,
        last_downloaded_file_path=result.downloaded_file_path,
        last_final_page_url=result.final_page_url,
        onsite_capture_path=result.onsite_capture_path,
        onsite_capture_format=result.onsite_capture_format,
        onsite_page_count=result.onsite_page_count,
        onsite_completeness_status=result.onsite_completeness_status,
    )
    route_record_checksum = _route_record_checksum(route_record_request)
    route_record_key = _idempotency_key_with_checksum(
        normalize_url(result.normalized_url),
        result.route_kind,
        result.outcome,
        checksum=route_record_checksum,
    )
    existing_route_record = _lookup_idempotency_record(
        db_path=request.reports_db,
        scope=_REPORT_DOWNLOAD_ROUTE_RECORD_SCOPE,
        idempotency_key=route_record_key,
        input_checksum=route_record_checksum,
        ctx=ctx,
    )
    if existing_route_record is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_route_record_idempotency_reused",
                module=logger.name,
                fields={
                    "normalized_url": result.normalized_url,
                    "route_kind": result.route_kind,
                    "outcome": result.outcome,
                },
            )
        )
    else:
        deps.record_publisher_download_route(
            route_record_request,
            ctx,
        )
        _record_idempotency_outcome(
            db_path=request.reports_db,
            scope=_REPORT_DOWNLOAD_ROUTE_RECORD_SCOPE,
            idempotency_key=route_record_key,
            input_checksum=route_record_checksum,
            outcome_payload={
                "schema_version": "1.0",
                "normalized_url": result.normalized_url,
                "route_kind": result.route_kind,
                "route_family": result.route_family,
                "route_status": result.route_status,
                "outcome": result.outcome,
            },
            artifact_references={
                "resolved_target_url": result.resolved_target_url,
                "last_final_page_url": result.final_page_url,
                "last_downloaded_file_path": result.downloaded_file_path or "",
                "onsite_capture_path": result.onsite_capture_path or "",
            },
            ctx=ctx,
        )
    _evaluate_route_playbook_promotion(
        request=request,
        result=result,
        ctx=ctx,
        dependencies=deps,
        route_record_reused=existing_route_record is not None,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_publisher_route_recorded",
            module=logger.name,
            fields={
                "normalized_url": result.normalized_url,
                "reports_db": request.reports_db,
                "route_kind": result.route_kind,
                "outcome": result.outcome,
            },
        )
    )
    if result.outcome == "downloaded" and result.downloaded_file_path:
        file_hash = deps.file_md5(
            FileHashRequest(
                schema_version="1.0",
                path=result.downloaded_file_path,
            ),
            ctx,
        )
        source_record_request = ReportSourceRecordRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            source_domain=_source_domain_for_url(result.source_url),
            report_name=_report_name_for_result(result),
            landing_page_url=result.source_url,
            downloaded_at_utc=_utc_now_iso(),
            md5=file_hash.md5,
        )
        source_record_checksum = sha256_json(
            {
                "schema_version": "1.0",
                "source_domain": source_record_request.source_domain,
                "report_name": source_record_request.report_name,
                "landing_page_url": source_record_request.landing_page_url,
                "md5": source_record_request.md5,
            }
        )
        source_record_key = _idempotency_key_with_checksum(
            normalize_url(source_record_request.landing_page_url),
            checksum=source_record_checksum,
        )
        existing_source_record = _lookup_idempotency_record(
            db_path=request.reports_db,
            scope=_REPORT_DOWNLOAD_SOURCE_RECORD_SCOPE,
            idempotency_key=source_record_key,
            input_checksum=source_record_checksum,
            ctx=ctx,
        )
        if existing_source_record is not None:
            source_record = _restore_report_source_record(
                dict(existing_source_record.outcome_payload or {})
            )
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="report_download_source_record_idempotency_reused",
                    module=logger.name,
                    fields={
                        "landing_page_url": source_record.landing_page_url,
                        "record_id": source_record.record_id,
                        "md5": source_record.md5,
                    },
                )
            )
        else:
            source_record = run_with_retry(
                step_name="report_download_source_record",
                operation=lambda: deps.record_report_source(
                    source_record_request,
                    ctx,
                ),
                ctx=ctx,
                logger=logger,
                module_name=logger.name,
                policy=policy,
                retry_event="report_download_source_record_retry",
                failure_event="report_download_source_record_failed",
                sleep_fn=deps.sleep_fn,
            )
            _record_idempotency_outcome(
                db_path=request.reports_db,
                scope=_REPORT_DOWNLOAD_SOURCE_RECORD_SCOPE,
                idempotency_key=source_record_key,
                input_checksum=source_record_checksum,
                outcome_payload=asdict(source_record),
                artifact_references={
                    "record_id": source_record.record_id,
                    "landing_page_url": source_record.landing_page_url,
                    "md5": source_record.md5,
                },
                ctx=ctx,
            )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_source_recorded",
                module=logger.name,
                fields={
                    "record_id": source_record.record_id,
                    "reports_db": request.reports_db,
                    "source_domain": source_record.source_domain,
                    "report_name": source_record.report_name,
                    "landing_page_url": source_record.landing_page_url,
                    "downloaded_at_utc": source_record.downloaded_at_utc,
                    "md5": source_record.md5,
                },
            )
        )
        report_value_score = deps.score_report_value(
            ReportValueScoreRequest(
                schema_version="1.0",
                publisher_name="",
                source_domain=source_record.source_domain,
                report_name=source_record.report_name,
                landing_page_url=source_record.landing_page_url,
                source_page_url=source_record.landing_page_url,
                source_status="downloaded",
                discovered_at_utc="",
                downloaded_at_utc=source_record.downloaded_at_utc,
                md5=source_record.md5,
                evaluation_year=_utc_now_year(),
            ),
            ctx,
        )
        run_with_retry(
            step_name="report_download_source_value_score_record",
            operation=lambda: deps.record_report_value_score(
                ReportValueScoreRecordRequest(
                    schema_version="1.0",
                    db_path=request.reports_db,
                    record_id=source_record.record_id,
                    score=report_value_score,
                    scored_at_utc=_utc_now_iso(),
                ),
                ctx,
            ),
            ctx=ctx,
            logger=logger,
            module_name=logger.name,
            policy=policy,
            retry_event="report_download_source_value_score_record_retry",
            failure_event="report_download_source_value_score_record_failed",
            sleep_fn=deps.sleep_fn,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_source_value_scored",
                module=logger.name,
                fields={
                    "record_id": source_record.record_id,
                    "landing_page_url": source_record.landing_page_url,
                    "overall_score": report_value_score.overall_score,
                    "value_band": report_value_score.value_band,
                    "component_scores": {
                        component.dimension: component.score
                        for component in report_value_score.components
                    },
                    "rationale": report_value_score.rationale,
                },
            )
        )
    identity_upsert_request = BrowserDownloadIdentityFieldUpsertRequest(
        schema_version="1.0",
        path=request.settings.identity_config_path,
        encountered_form_fields=result.encountered_form_fields,
    )
    identity_update_checksum = _identity_update_checksum(identity_upsert_request)
    identity_update_key = _idempotency_key_with_checksum(
        request.settings.identity_config_path,
        checksum=identity_update_checksum,
    )
    existing_identity_update = _lookup_idempotency_record(
        db_path=request.reports_db,
        scope=_REPORT_DOWNLOAD_IDENTITY_UPDATE_SCOPE,
        idempotency_key=identity_update_key,
        input_checksum=identity_update_checksum,
        ctx=ctx,
    )
    if existing_identity_update is not None:
        identity_update = _restore_identity_update_response(
            dict(existing_identity_update.outcome_payload or {})
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_identity_update_idempotency_reused",
                module=logger.name,
                fields={
                    "path": identity_update.path,
                    "added_field_keys": identity_update.added_field_keys,
                    "total_fields": identity_update.total_fields,
                },
            )
        )
    else:
        identity_update = deps.upsert_browser_download_identity_fields(
            identity_upsert_request,
            ctx,
        )
        _record_idempotency_outcome(
            db_path=request.reports_db,
            scope=_REPORT_DOWNLOAD_IDENTITY_UPDATE_SCOPE,
            idempotency_key=identity_update_key,
            input_checksum=identity_update_checksum,
            outcome_payload=_identity_update_response_payload(identity_update),
            artifact_references={
                "path": identity_update.path,
                "added_field_keys": list(identity_update.added_field_keys or []),
            },
            ctx=ctx,
        )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_identity_updated",
            module=logger.name,
            fields={
                "path": identity_update.path,
                "added_field_keys": identity_update.added_field_keys,
                "total_fields": identity_update.total_fields,
            },
        )
    )

    drive_uploads = _archive_successful_report_artifacts(
        request=request,
        result=result,
        normalized_url=normalized_url,
        policy=policy,
        ctx=ctx,
        dependencies=deps,
    )
    response = ReportDownloadOrchestratorResult(
        schema_version="1.0",
        source_url=result.source_url,
        normalized_url=result.normalized_url,
        route_kind=result.route_kind,
        route_family=result.route_family,
        route_status=result.route_status,
        outcome=result.outcome,
        route_summary=result.route_summary,
        final_page_url=result.final_page_url,
        resolved_target_url=result.resolved_target_url,
        used_memory_route=result.used_route_hint,
        route_steps=result.route_steps,
        confirmation_evidence=result.confirmation_evidence,
        terminal_evidence=result.terminal_evidence,
        browser_had_structured_result=result.browser_had_structured_result,
        used_candidate_pdf_url=result.used_candidate_pdf_url,
        used_candidate_source_page=result.used_candidate_source_page,
        encountered_form_fields=result.encountered_form_fields,
        identity_fields_added=identity_update.added_field_keys,
        blocked_reason=result.blocked_reason,
        blocked_reason_detail=result.blocked_reason_detail,
        downloaded_file_path=result.downloaded_file_path,
        downloaded_file_name=result.downloaded_file_name,
        downloaded_mime_type=result.downloaded_mime_type,
        downloaded_size_bytes=result.downloaded_size_bytes,
        onsite_capture_path=result.onsite_capture_path,
        onsite_capture_format=result.onsite_capture_format,
        onsite_page_count=result.onsite_page_count,
        onsite_completeness_status=result.onsite_completeness_status,
        drive_uploads=drive_uploads,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_complete",
            module=logger.name,
            fields={
                "normalized_url": response.normalized_url,
                "route_kind": response.route_kind,
                "outcome": response.outcome,
                "used_memory_route": response.used_memory_route,
                "downloaded_file_path": response.downloaded_file_path or "",
                "drive_upload_count": len(response.drive_uploads),
            },
        )
    )
    return response


def _run_download_attempt(
    *,
    request: ReportDownloadOrchestratorRequest,
    ctx: RunContext,
    policy: RetryPolicy,
    dependencies: ReportDownloadDependencies,
    planned_step: ReportDownloadRoutePlanStep,
) -> BrowserReportDownloadResult:
    service_request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url=request.url,
        settings=request.settings,
        delivery_email=request.delivery_email,
        route_hint=planned_step.route_hint,
        route_step_hints=list(planned_step.route_step_hints),
        route_kind_hint=planned_step.route_kind_hint,
        candidate_trace=request.candidate_trace,
        publisher_discovery_route_kind=request.publisher_discovery_route_kind,
        publisher_recommended_discovery_route_kind=request.publisher_recommended_discovery_route_kind,
        attempt_url=planned_step.attempt_url,
        route_family_hint=planned_step.route_family,
        source_page_url_hint=planned_step.source_page_url_hint,
    )

    def _attempt_operation() -> BrowserReportDownloadResult:
        try:
            return dependencies.download_report_with_browser_use(service_request, ctx)
        except AppError as exc:
            pack: FailedAcquisitionForensicsPack | None = None
            try:
                pack = _persist_failed_attempt_forensics_pack(
                    request=request,
                    planned_step=planned_step,
                    exc=exc,
                    ctx=ctx,
                    dependencies=dependencies,
                )
            except AppError as pack_exc:
                logger.info(
                    log_event(
                        ctx,
                        role="orchestrator",
                        event="report_download_failure_forensics_persist_failed",
                        module=logger.name,
                        fields={
                            "normalized_url": service_request.url,
                            "step_name": planned_step.step_name,
                            "route_family": planned_step.route_family,
                            "error_code": exc.code,
                            "forensics_error_code": pack_exc.code,
                            "forensics_error_message": pack_exc.message,
                        },
                    )
                )
            raise _with_failure_forensics_context(
                exc,
                pack=pack,
                terminal_evidence=_terminal_evidence_from_error_context(
                    exc=exc,
                    request=request,
                    planned_step=planned_step,
                ),
            ) from exc

    return run_with_retry(
        step_name=planned_step.step_name,
        operation=_attempt_operation,
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=policy,
        retry_event="report_download_retry",
        failure_event="report_download_attempt_failed",
        failure_fields_builder=lambda exc, attempt, retryable: {
            "step": planned_step.step_name,
            "attempt": attempt,
            "retryable": retryable,
            "route_family": planned_step.route_family,
            "recovery_class": planned_step.recovery_class or planned_step.route_family,
            "recovery_decision": planned_step.recovery_decision,
            "attempt_url": str(planned_step.attempt_url or request.url).strip(),
            "code": exc.code if isinstance(exc, AppError) else "unexpected_exception",
            "error": (exc.message if isinstance(exc, AppError) else str(exc)),
            "error_class": _failure_error_class(exc),
            "failure_forensics_pack_path": (
                str((exc.context or {}).get("failure_forensics_pack_path") or "")
                if isinstance(exc, AppError)
                else ""
            ),
            "failure_forensics_artifact_policy": (
                str((exc.context or {}).get("failure_forensics_artifact_policy") or "")
                if isinstance(exc, AppError)
                else ""
            ),
            "terminal_html_snapshot_path": (
                str((exc.context or {}).get("terminal_html_snapshot_path") or "")
                if isinstance(exc, AppError)
                else ""
            ),
            "terminal_screenshot_path": (
                str((exc.context or {}).get("terminal_screenshot_path") or "")
                if isinstance(exc, AppError)
                else ""
            ),
            "blocked_reason": (
                str((exc.context or {}).get("blocked_reason") or "")
                if isinstance(exc, AppError)
                else ""
            ),
        },
        is_retryable=lambda exc: _is_download_operation_retryable(
            exc=exc,
            planned_step=planned_step,
        ),
        sleep_fn=dependencies.sleep_fn,
    )


def _archive_successful_report_artifacts(
    *,
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult,
    normalized_url: str,
    policy: RetryPolicy,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> list[ReportDownloadDriveUpload]:
    if not request.settings.drive_upload_enabled:
        return []
    if result.outcome not in {"downloaded", "captured"}:
        return []
    artifact_paths = _local_terminal_artifact_paths(result)
    if not artifact_paths:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_upload_no_artifacts",
                module=logger.name,
                fields={"normalized_url": normalized_url, "outcome": result.outcome},
            )
        )
        return []
    try:
        folder_id = _resolve_drive_upload_folder_id(
            request=request,
            normalized_url=normalized_url,
            ctx=ctx,
            dependencies=dependencies,
        )
        uploads = []
        for path in artifact_paths:
            uploads.append(
                _archive_single_artifact(
                    request=request,
                    result=result,
                    normalized_url=normalized_url,
                    local_path=path,
                    folder_id=folder_id,
                    policy=policy,
                    ctx=ctx,
                    dependencies=dependencies,
                )
            )
        return uploads
    except AppError:
        if request.settings.drive_upload_required:
            raise
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_upload_best_effort_failed",
                module=logger.name,
                fields={"normalized_url": normalized_url},
            )
        )
        return []


def _resolve_drive_upload_folder_id(
    *,
    request: ReportDownloadOrchestratorRequest,
    normalized_url: str,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> str:
    explicit_folder_id = extract_drive_folder_id(request.publisher_google_folder or "")
    if explicit_folder_id:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_folder_resolved",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "resolution_source": "request_publisher_google_folder",
                    "folder_id": explicit_folder_id,
                },
            )
        )
        return explicit_folder_id
    lookup = dependencies.get_report_download_drive_folder(
        ReportDownloadDriveFolderLookupRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            normalized_landing_page_url=normalized_url,
            publisher_insights_url=request.publisher_insights_url,
        ),
        ctx,
    )
    folder_id = extract_drive_folder_id(lookup.google_folder if lookup else "")
    if folder_id:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_folder_resolved",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "resolution_source": lookup.resolution_source if lookup else "",
                    "publisher_name": lookup.publisher_name if lookup else "",
                    "folder_id": folder_id,
                },
            )
        )
        return folder_id
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_drive_folder_missing",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "has_publisher_insights_url": bool(request.publisher_insights_url),
            },
        )
    )
    raise AppError(
        code="report_download_drive_folder_missing",
        message="Publisher Drive folder could not be resolved for acquired report archival",
        retryable=False,
        severity="error",
        context={
            "normalized_url": normalized_url,
            "publisher_insights_url": request.publisher_insights_url or "",
        },
    )


def _archive_single_artifact(
    *,
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult,
    normalized_url: str,
    local_path: str,
    folder_id: str,
    policy: RetryPolicy,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
) -> ReportDownloadDriveUpload:
    path = Path(local_path)
    file_name = path.name
    mime_type = _mime_type_for_artifact(result=result, path=path)
    file_hash = dependencies.file_md5(
        FileHashRequest(schema_version="1.0", path=str(path)),
        ctx,
    )
    size = path.stat().st_size
    upload_checksum = sha256_json(
        {
            "schema_version": "1.0",
            "folder_id": folder_id,
            "normalized_url": normalized_url,
            "file_name": file_name,
            "mime_type": mime_type,
            "size": size,
            "md5": file_hash.md5,
        }
    )
    upload_key = _idempotency_key_with_checksum(
        folder_id,
        normalized_url,
        file_name,
        checksum=upload_checksum,
    )
    existing_upload = _lookup_idempotency_record(
        db_path=request.reports_db,
        scope=_REPORT_DOWNLOAD_DRIVE_UPLOAD_SCOPE,
        idempotency_key=upload_key,
        input_checksum=upload_checksum,
        ctx=ctx,
    )
    if existing_upload is not None:
        upload = _restore_drive_upload(dict(existing_upload.outcome_payload or {}))
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_upload_idempotency_reused",
                module=logger.name,
                fields={
                    "local_path": upload.local_path,
                    "folder_id": upload.folder_id,
                    "file_name": upload.file_name,
                    "status": upload.status,
                    "drive_file_id": upload.drive_file.file_id,
                    "md5": upload.md5 or "",
                },
            )
        )
        return upload
    duplicate = _find_duplicate_drive_file(
        request=request,
        folder_id=folder_id,
        file_name=file_name,
        md5=file_hash.md5,
        policy=policy,
        ctx=ctx,
        dependencies=dependencies,
    )
    if duplicate is not None:
        upload = ReportDownloadDriveUpload(
            schema_version="1.0",
            local_path=str(path),
            file_name=file_name,
            mime_type=mime_type,
            folder_id=folder_id,
            status="skipped_duplicate",
            size=size,
            md5=file_hash.md5,
            drive_file=duplicate,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_drive_upload_skipped_duplicate",
                module=logger.name,
                fields={
                    "local_path": upload.local_path,
                    "folder_id": folder_id,
                    "file_name": file_name,
                    "drive_file_id": duplicate.file_id,
                    "md5": file_hash.md5,
                },
            )
        )
        _record_idempotency_outcome(
            db_path=request.reports_db,
            scope=_REPORT_DOWNLOAD_DRIVE_UPLOAD_SCOPE,
            idempotency_key=upload_key,
            input_checksum=upload_checksum,
            outcome_payload=asdict(upload),
            artifact_references={
                "folder_id": upload.folder_id,
                "file_name": upload.file_name,
                "drive_file_id": upload.drive_file.file_id,
                "md5": upload.md5,
                "status": upload.status,
            },
            ctx=ctx,
        )
        return upload
    upload_response = run_with_retry(
        step_name="report_download_drive_upload",
        operation=lambda: dependencies.upload_local_file(
            DriveUploadLocalFileRequest(
                schema_version="1.0",
                folder_id=folder_id,
                service_account_path=request.settings.drive_upload_google_sa_path,
                source_path=str(path),
                file_name=file_name,
                mime_type=mime_type,
                supports_all_drives=request.settings.drive_upload_supports_all_drives,
                auth_mode=request.settings.drive_upload_auth_mode,
                oauth_client_path=request.settings.drive_upload_oauth_client_path,
                oauth_token_path=request.settings.drive_upload_oauth_token_path,
            ),
            ctx,
        ),
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=policy,
        retry_event="report_download_drive_upload_retry",
        failure_event="report_download_drive_upload_failed",
        sleep_fn=dependencies.sleep_fn,
    )
    upload = ReportDownloadDriveUpload(
        schema_version="1.0",
        local_path=str(path),
        file_name=file_name,
        mime_type=mime_type,
        folder_id=folder_id,
        status="uploaded",
        size=upload_response.size,
        md5=upload_response.md5,
        drive_file=upload_response.file,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_drive_uploaded",
            module=logger.name,
            fields={
                "local_path": upload.local_path,
                "folder_id": folder_id,
                "file_name": file_name,
                "drive_file_id": upload.drive_file.file_id,
                "size": upload.size,
                "md5": upload.md5 or "",
            },
        )
    )
    _record_idempotency_outcome(
        db_path=request.reports_db,
        scope=_REPORT_DOWNLOAD_DRIVE_UPLOAD_SCOPE,
        idempotency_key=upload_key,
        input_checksum=upload_checksum,
        outcome_payload=asdict(upload),
        artifact_references={
            "folder_id": upload.folder_id,
            "file_name": upload.file_name,
            "drive_file_id": upload.drive_file.file_id,
            "md5": upload.md5,
            "status": upload.status,
        },
        ctx=ctx,
    )
    return upload


def _find_duplicate_drive_file(
    *,
    request: ReportDownloadOrchestratorRequest,
    folder_id: str,
    file_name: str,
    md5: str,
    policy: RetryPolicy,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
):
    response = run_with_retry(
        step_name="report_download_drive_duplicate_check",
        operation=lambda: dependencies.list_files_in_folder(
            DriveFolderFileListRequest(
                schema_version="1.0",
                folder_id=folder_id,
                service_account_path=request.settings.drive_upload_google_sa_path,
                name_prefix=file_name,
                supports_all_drives=request.settings.drive_upload_supports_all_drives,
                include_items_from_all_drives=(
                    request.settings.drive_upload_include_items_from_all_drives
                ),
                drive_id=request.settings.drive_upload_drive_id,
                auth_mode=request.settings.drive_upload_auth_mode,
                oauth_client_path=request.settings.drive_upload_oauth_client_path,
                oauth_token_path=request.settings.drive_upload_oauth_token_path,
            ),
            ctx,
        ),
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=policy,
        retry_event="report_download_drive_duplicate_check_retry",
        failure_event="report_download_drive_duplicate_check_failed",
        sleep_fn=dependencies.sleep_fn,
    )
    for file in response.files:
        if (file.name or "") == file_name and (file.md5_checksum or "") == md5:
            return file
    return None


def _local_terminal_artifact_paths(result: BrowserReportDownloadResult) -> list[str]:
    candidates = [
        result.downloaded_file_path,
        result.onsite_capture_path,
        result.terminal_evidence.html_snapshot_path,
        result.terminal_evidence.screenshot_path,
    ]
    seen: set[str] = set()
    paths: list[str] = []
    for candidate in candidates:
        value = str(candidate or "").strip()
        if not value:
            continue
        key = _local_artifact_identity_key(value)
        if key in seen:
            continue
        seen.add(key)
        paths.append(value)
    return paths


def _local_artifact_identity_key(value: str) -> str:
    path = Path(value)
    try:
        return str(path.resolve(strict=False)).casefold()
    except OSError:
        return str(path).casefold()


def _mime_type_for_artifact(*, result: BrowserReportDownloadResult, path: Path) -> str:
    if result.downloaded_file_path and Path(result.downloaded_file_path) == path:
        return result.downloaded_mime_type or "application/octet-stream"
    if result.onsite_capture_path and Path(result.onsite_capture_path) == path:
        if result.onsite_capture_format in {"html", "html+markdown"}:
            return "text/html"
        if result.onsite_capture_format == "markdown":
            return "text/markdown"
    guessed, _ = mimetypes.guess_type(str(path))
    return guessed or "application/octet-stream"


def _is_download_attempt_retryable(
    *,
    exc: Exception,
    planned_step: ReportDownloadRoutePlanStep,
) -> bool:
    if not is_retryable_app_error(exc):
        return False
    if not isinstance(exc, AppError):
        return False
    if planned_step.route_family.startswith("browser_") and exc.code in {
        "browser_download_agent_timeout",
        "browser_download_route_summary_too_weak",
    }:
        return False
    return True


def _is_download_operation_retryable(
    *,
    exc: Exception,
    planned_step: ReportDownloadRoutePlanStep,
) -> bool:
    if not _is_download_attempt_retryable(exc=exc, planned_step=planned_step):
        return False
    if not isinstance(exc, AppError):
        return False
    if (
        planned_step.route_family in {"direct_pdf_probe", "http_pdf_probe"}
        and exc.code == "browser_download_http_probe_failed"
    ):
        return False
    if (
        planned_step.route_family.startswith("browser_")
        and exc.code == "browser_download_pdf_fetch_failed"
    ):
        return False
    return True


def _remembered_route_memory(
    remembered_route: PublisherDownloadRouteResponse | None,
) -> PublisherDownloadRouteMemory | None:
    if remembered_route is None:
        return None
    return PublisherDownloadRouteMemory(
        schema_version="1.0",
        route_kind=remembered_route.route_kind,
        route_summary=remembered_route.route_summary,
        route_steps=list(remembered_route.route_steps),
        outcome=remembered_route.outcome,
        route_family=remembered_route.route_family,
        route_status=remembered_route.route_status,
        resolved_target_url=remembered_route.resolved_target_url,
        attempts=remembered_route.attempts,
        verified_successes=remembered_route.verified_successes,
        last_n_outcomes=list(remembered_route.last_n_outcomes),
        confidence_score=remembered_route.confidence_score,
        exact_route_found=remembered_route.exact_route_found,
        browser_had_structured_result=remembered_route.browser_had_structured_result,
        onsite_completeness_status=remembered_route.onsite_completeness_status,
        route_policy=list(remembered_route.route_policy),
        publisher_route_policy=list(remembered_route.publisher_route_policy),
    )


def _publisher_scope_url_for_request(
    request: ReportDownloadOrchestratorRequest,
) -> str | None:
    if request.publisher_insights_url:
        return request.publisher_insights_url
    if request.candidate_trace is not None:
        for source_page_url in request.candidate_trace.source_page_urls:
            token = str(source_page_url or "").strip()
            if token:
                return token
    return request.url


def _source_domain_for_url(url: str) -> str:
    return str(urlsplit(str(url).strip()).hostname or "").strip().lower()


def _assert_candidate_download_ready(
    *,
    request: ReportDownloadOrchestratorRequest,
    normalized_url: str,
    ctx: RunContext,
) -> None:
    candidate = request.candidate_trace
    if candidate is None:
        return
    if candidate.pdf_url or normalized_url.endswith(".pdf"):
        return
    readiness_score, rejection_reason, readiness_signals = (
        _evaluate_candidate_download_readiness(
            request=request,
            normalized_url=normalized_url,
        )
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_readiness_evaluated",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "candidate_title": candidate.title,
                "candidate_url": candidate.canonical_url,
                "download_readiness_score": readiness_score,
                "readiness_signals": readiness_signals,
                "readiness_rejection_reason": rejection_reason or "",
            },
        )
    )
    if rejection_reason:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_readiness_rejected",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "candidate_title": candidate.title,
                    "candidate_url": candidate.canonical_url,
                    "download_readiness_score": readiness_score,
                    "readiness_signals": readiness_signals,
                    "readiness_rejection_reason": rejection_reason,
                },
            )
        )
        raise AppError(
            code=f"report_download_{rejection_reason}",
            message="The candidate URL does not look like a report acquisition target",
            retryable=False,
            context={
                "normalized_url": normalized_url,
                "candidate_title": candidate.title,
                "candidate_url": candidate.canonical_url,
                "download_readiness_score": readiness_score,
                "readiness_signals": readiness_signals,
                "readiness_rejection_reason": rejection_reason,
            },
        )


def _evaluate_candidate_download_readiness(
    *,
    request: ReportDownloadOrchestratorRequest,
    normalized_url: str,
) -> tuple[float, str | None, list[str]]:
    candidate = request.candidate_trace
    if candidate is None:
        return 1.0, None, ["no_candidate_trace"]
    title = str(candidate.title or "").strip().casefold()
    url_value = str(candidate.canonical_url or normalized_url).strip().casefold()
    source_pages = [
        str(value or "").strip().casefold() for value in candidate.source_page_urls
    ]
    provenances = {
        str(value or "").strip().casefold() for value in candidate.discovery_provenances
    }
    score = 0.0
    signals: list[str] = []
    if any(marker in title for marker in _REPORT_TITLE_MARKERS):
        score += 0.5
        signals.append("report_title_marker")
    if any(marker in url_value for marker in _REPORT_TITLE_MARKERS):
        score += 0.25
        signals.append("report_url_marker")
    if any(marker in url_value for marker in _REPORT_RESOURCE_URL_MARKERS):
        score += 0.15
        signals.append("report_resource_url_marker")
    if any(
        any(marker in page for marker in _REPORT_SOURCE_PAGE_MARKERS)
        for page in source_pages
    ):
        score += 0.2
        signals.append("report_source_page")
    if candidate.max_confidence is not None:
        score += min(0.2, max(0.0, float(candidate.max_confidence)) * 0.2)
        signals.append("candidate_confidence")
    if "direct_pdf_source" in provenances:
        score += 0.3
        signals.append("direct_pdf_source")
    if (
        "browser_dom" in provenances
        or "browser_rendered_html_supplement" in provenances
    ):
        score += 0.1
        signals.append("browser_provenance")

    if any(marker in url_value for marker in _ASSET_URL_MARKERS):
        score -= 0.9
        signals.append("asset_url_marker")
        return round(score, 3), "candidate_rejected_asset_page", signals
    if any(marker in url_value for marker in _MARKETING_URL_MARKERS):
        score -= 0.7
        signals.append("marketing_url_marker")
    if any(marker in url_value for marker in _NON_REPORT_URL_MARKERS):
        score -= 0.6
        signals.append("non_report_url_marker")
    if any(marker in title for marker in _NON_REPORT_TITLE_MARKERS):
        score -= 0.7
        signals.append("non_report_title_marker")
    if _is_mixed_content_hub_candidate(
        url_value=url_value,
        title=title,
        source_pages=source_pages,
        normalized_url=normalized_url,
        has_pdf_url=bool(str(candidate.pdf_url or "").strip()),
    ):
        score -= 0.6
        signals.append("mixed_content_hub_candidate")
        return round(score, 3), "candidate_rejected_mixed_content_hub", signals

    if score >= 0.35:
        return round(score, 3), None, signals
    if any(marker in url_value for marker in _MARKETING_URL_MARKERS):
        return round(score, 3), "candidate_rejected_marketing_page", signals
    if any(marker in title for marker in _NON_REPORT_TITLE_MARKERS) or any(
        marker in url_value for marker in _NON_REPORT_URL_MARKERS
    ):
        return round(score, 3), "candidate_rejected_non_report", signals
    return round(score, 3), "candidate_rejected_non_report", signals


def _is_mixed_content_hub_candidate(
    *,
    url_value: str,
    title: str,
    source_pages: list[str],
    normalized_url: str,
    has_pdf_url: bool,
) -> bool:
    if has_pdf_url:
        return False
    parsed = urlsplit(str(url_value or normalized_url).strip())
    path = str(parsed.path or "").strip().casefold()
    if path.endswith(".pdf"):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return True
    last_segment = segments[-1]
    last_tokens = [
        token for token in last_segment.replace("_", "-").split("-") if token
    ]
    title_has_detail_signal = any(
        marker in str(title or "") for marker in _REPORT_DETAIL_TITLE_MARKERS
    )
    path_has_year = re.search(r"\b20\d{2}\b", path) is not None
    if title_has_detail_signal and (len(last_tokens) >= 3 or path_has_year):
        return False
    source_page_set = {
        _url_surface_key(value) for value in source_pages if str(value or "").strip()
    }
    candidate_surface_key = _url_surface_key(str(url_value or normalized_url))
    source_same_surface = (
        bool(source_page_set) and candidate_surface_key in source_page_set
    )
    listing_last_segment = last_segment in _MIXED_CONTENT_HUB_SEGMENTS
    listing_query = any(
        key in str(parsed.query or "").casefold()
        for key in ("page=", "offset=", "category=", "tag=", "filter=", "search=")
    )
    short_listing_under_context = (
        len(segments) <= 2
        and any(segment in _MIXED_CONTENT_HUB_SEGMENTS for segment in segments)
        and len(last_tokens) < 3
    )
    return (
        source_same_surface
        or listing_last_segment
        or listing_query
        or short_listing_under_context
    )


def _url_surface_key(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    host = str(parsed.hostname or "").strip().casefold()
    path = "/".join(segment for segment in str(parsed.path or "").split("/") if segment)
    return f"{host}/{path}".rstrip("/")


def _report_name_for_result(result: BrowserReportDownloadResult) -> str:
    file_name = str(result.downloaded_file_name or "").strip()
    path_value = str(result.downloaded_file_path or "").strip()
    if file_name:
        base_name = Path(file_name).stem
    elif path_value:
        base_name = Path(path_value).stem
    else:
        base_name = "downloaded_report"
    return " ".join(base_name.replace("_", " ").replace("-", " ").split()).strip()


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _utc_now_year() -> int:
    return datetime.now(timezone.utc).year


__all__ = [name for name in globals() if not name.startswith("__")]
