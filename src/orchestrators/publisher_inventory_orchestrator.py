from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import asdict, dataclass, is_dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlsplit

from src.contracts.drive import (
    DriveDownloadRequest,
    DriveDownloadResponse,
    DriveFile,
    DriveFolderFileListRequest,
    DriveFolderFileListResponse,
    DriveUploadBytesRequest,
    DriveUploadBytesResponse,
)
from src.contracts.idempotency import (
    OrchestratorIdempotencyGetRequest,
    OrchestratorIdempotencyRecordRequest,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryBuildRequest,
    PublisherInventoryBuildResponse,
    PublisherInventoryCandidateQualityRequest,
    PublisherInventoryCandidateQualityResponse,
    PublisherInventoryCandidateScreeningItem,
    PublisherInventoryCandidateScreeningRequest,
    PublisherInventoryCandidateScreeningResponse,
    PublisherInventoryCoverageValidationRequest,
    PublisherInventoryCoverageValidationResponse,
    PublisherInventoryDiscoveryRequest,
    PublisherInventoryDiscoveryResult,
    PublisherInventoryDiffItem,
    PublisherInventoryRecoveryRecord,
    PublisherInventoryRoutePlanRequest,
    PublisherInventoryRunQualityEvaluationRequest,
    PublisherInventoryRunQualitySummary,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
    PublisherInventorySnapshot,
)
from src.contracts.report_store import (
    PublisherResourceRankingPolicy,
    PublisherResourceRankingRequest,
    PublisherResourceRankingResponse,
    PublisherInventoryRecoveryCacheGetRequest,
    PublisherInventoryRecoveryCacheRecordRequest,
    PublisherInventoryRunQualityRecordRequest,
    ReportSourceQualityHistoryRequest,
    ReportSourceQualityHistoryResponse,
    ReportSourceDiscoveryRecordRequest,
    ReportSourceDiscoveryRecordResponse,
    PublisherInventoryStateGetRequest,
    PublisherInventoryStateRecordRequest,
    PublisherInventoryStateResponse,
    PublisherInventoryTestStatusRecordRequest,
)
from src.contracts.run_context import RunContext
from src.generators.publisher_inventory_generator import (
    build_publisher_inventory_snapshot,
    parse_publisher_inventory_snapshot,
)
from src.generators.publisher_inventory_coverage_generator import (
    validate_publisher_inventory_coverage,
)
from src.generators.publisher_inventory_run_quality_generator import (
    evaluate_publisher_inventory_run_quality,
)
from src.generators.publisher_inventory_candidate_screening_generator import (
    screen_publisher_inventory_candidates,
)
from src.generators.publisher_inventory_candidate_quality_generator import (
    qualify_publisher_inventory_candidates,
)
from src.generators.report_value_generator import rank_publisher_resources
from src.orchestrators._publisher_inventory_orchestrator.route_planner import (
    plan_publisher_inventory_routes,
)
from src.orchestrators.retry_orchestrator import (
    RetryPolicy,
    is_retryable_app_error,
    run_with_retry,
)
from src.services import idempotency_service
from src.services.drive_service import download_pdf, list_files_in_folder, upload_bytes
from src.services.publisher_inventory_service import discover_publisher_inventory
from src.services.report_store_service import (
    get_publisher_inventory_recovery_cache_record,
    get_publisher_inventory_state,
    record_publisher_inventory_recovery_cache_record,
    record_publisher_inventory_run_quality,
    record_discovered_report_source,
    list_report_source_quality_history,
    record_publisher_inventory_state,
    record_publisher_inventory_test_status,
)
from src.utils.drive_utils import extract_drive_folder_id
from src.utils.cache_utils import sha256_json
from src.utils.coercion import coerce_int
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.publisher_inventory_orchestrator")

_SNAPSHOT_PREFIX = "publisher_inventory_snapshot__"
_SNAPSHOT_LOOKBACK_LIMIT = 10
_RUN_QUALITY_IDEMPOTENCY_SCOPE = "publisher_inventory_orchestrator.run_quality_record"
_RECOVERY_CACHE_IDEMPOTENCY_SCOPE = (
    "publisher_inventory_orchestrator.recovery_cache_record"
)
_SNAPSHOT_UPLOAD_IDEMPOTENCY_SCOPE = "publisher_inventory_orchestrator.snapshot_upload"
_REPORT_SOURCE_RECORD_IDEMPOTENCY_SCOPE = (
    "publisher_inventory_orchestrator.report_source_record"
)
_STATE_RECORD_IDEMPOTENCY_SCOPE = "publisher_inventory_orchestrator.state_record"
_TEST_STATUS_IDEMPOTENCY_SCOPE = "publisher_inventory_orchestrator.test_status_record"


@dataclass(frozen=True)
class PublisherInventoryDependencies:
    discover_publisher_inventory: Callable[
        [PublisherInventoryServiceRequest, RunContext],
        PublisherInventoryServiceResponse,
    ]
    build_publisher_inventory_snapshot: Callable[
        [PublisherInventoryBuildRequest, RunContext],
        PublisherInventoryBuildResponse,
    ]
    validate_publisher_inventory_coverage: Callable[
        [PublisherInventoryCoverageValidationRequest, RunContext],
        PublisherInventoryCoverageValidationResponse,
    ]
    evaluate_publisher_inventory_run_quality: Callable[
        [PublisherInventoryRunQualityEvaluationRequest, RunContext],
        PublisherInventoryRunQualitySummary,
    ]
    parse_publisher_inventory_snapshot: Callable[
        [str, str, RunContext],
        PublisherInventorySnapshot,
    ]
    screen_publisher_inventory_candidates: Callable[
        [PublisherInventoryCandidateScreeningRequest, RunContext],
        PublisherInventoryCandidateScreeningResponse,
    ]
    qualify_publisher_inventory_candidates: Callable[
        [PublisherInventoryCandidateQualityRequest, RunContext],
        PublisherInventoryCandidateQualityResponse,
    ]
    get_publisher_inventory_state: Callable[
        [PublisherInventoryStateGetRequest, RunContext],
        Optional[PublisherInventoryStateResponse],
    ]
    get_publisher_inventory_recovery_cache_record: Callable[
        [PublisherInventoryRecoveryCacheGetRequest, RunContext],
        Optional[PublisherInventoryRecoveryRecord],
    ]
    record_publisher_inventory_run_quality: Callable[
        [PublisherInventoryRunQualityRecordRequest, RunContext],
        None,
    ]
    record_publisher_inventory_recovery_cache_record: Callable[
        [PublisherInventoryRecoveryCacheRecordRequest, RunContext],
        None,
    ]
    record_publisher_inventory_state: Callable[
        [PublisherInventoryStateRecordRequest, RunContext],
        None,
    ]
    record_publisher_inventory_test_status: Callable[
        [PublisherInventoryTestStatusRecordRequest, RunContext],
        None,
    ]
    record_discovered_report_source: Callable[
        [ReportSourceDiscoveryRecordRequest, RunContext],
        ReportSourceDiscoveryRecordResponse,
    ]
    list_report_source_quality_history: Callable[
        [ReportSourceQualityHistoryRequest, RunContext],
        ReportSourceQualityHistoryResponse,
    ]
    rank_publisher_resources: Callable[
        [PublisherResourceRankingRequest, RunContext],
        PublisherResourceRankingResponse,
    ]
    list_files_in_folder: Callable[
        [DriveFolderFileListRequest, RunContext],
        DriveFolderFileListResponse,
    ]
    download_pdf: Callable[[DriveDownloadRequest, RunContext], DriveDownloadResponse]
    upload_bytes: Callable[
        [DriveUploadBytesRequest, RunContext], DriveUploadBytesResponse
    ]

    @classmethod
    def default(cls) -> "PublisherInventoryDependencies":
        return cls(
            discover_publisher_inventory=discover_publisher_inventory,
            build_publisher_inventory_snapshot=build_publisher_inventory_snapshot,
            validate_publisher_inventory_coverage=validate_publisher_inventory_coverage,
            evaluate_publisher_inventory_run_quality=evaluate_publisher_inventory_run_quality,
            parse_publisher_inventory_snapshot=lambda snapshot_json, source, ctx: (
                parse_publisher_inventory_snapshot(
                    snapshot_json, source=source, ctx=ctx
                )
            ),
            screen_publisher_inventory_candidates=screen_publisher_inventory_candidates,
            qualify_publisher_inventory_candidates=qualify_publisher_inventory_candidates,
            get_publisher_inventory_state=get_publisher_inventory_state,
            get_publisher_inventory_recovery_cache_record=get_publisher_inventory_recovery_cache_record,
            record_publisher_inventory_run_quality=record_publisher_inventory_run_quality,
            record_publisher_inventory_recovery_cache_record=record_publisher_inventory_recovery_cache_record,
            record_publisher_inventory_state=record_publisher_inventory_state,
            record_publisher_inventory_test_status=record_publisher_inventory_test_status,
            record_discovered_report_source=record_discovered_report_source,
            list_report_source_quality_history=list_report_source_quality_history,
            rank_publisher_resources=rank_publisher_resources,
            list_files_in_folder=list_files_in_folder,
            download_pdf=download_pdf,
            upload_bytes=upload_bytes,
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


def _optional_dataclass_payload(value: object) -> dict[str, object] | None:
    if value is None:
        return None
    if not is_dataclass(value) or isinstance(value, type):
        return None
    return asdict(value)


def _run_quality_record_checksum(
    request: PublisherInventoryRunQualityRecordRequest,
) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "summary": asdict(request.summary),
        }
    )


def _state_record_checksum(
    request: PublisherInventoryStateRecordRequest,
) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "source_url": request.source_url,
            "route_kind": request.route_kind,
            "route_summary": request.route_summary,
            "route_trace": _optional_dataclass_payload(request.route_trace),
            "scenario_summary": _optional_dataclass_payload(request.scenario_summary),
            "last_final_page_url": request.last_final_page_url,
            "snapshot_drive_file_id": request.snapshot_drive_file_id,
            "snapshot_drive_file_name": request.snapshot_drive_file_name,
            "snapshot_sha256": request.snapshot_sha256,
        }
    )


def _test_status_record_checksum(
    request: PublisherInventoryTestStatusRecordRequest,
) -> str:
    return sha256_json(
        {
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "status": request.status,
        }
    )


def _recovery_cache_record_checksum(
    request: PublisherInventoryRecoveryCacheRecordRequest,
) -> str:
    record = request.record
    return sha256_json(
        {
            "schema_version": "1.0",
            "normalized_url": record.normalized_url,
            "canonical_url": record.canonical_url,
            "source_surface_class": record.source_surface_class,
            "verification_class": record.verification_class,
            "recovery_action": record.recovery_action,
            "last_outcome": record.last_outcome,
            "last_http_status": record.last_http_status,
            "last_error_marker": record.last_error_marker,
        }
    )


def _record_run_quality_if_needed(
    *,
    request: PublisherInventoryRunQualityRecordRequest,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> None:
    checksum = _run_quality_record_checksum(request)
    idempotency_key = _idempotency_key_with_checksum(
        request.normalized_url,
        request.summary.route_kind,
        request.summary.outcome,
        checksum=checksum,
    )
    existing = _lookup_idempotency_record(
        db_path=request.db_path,
        scope=_RUN_QUALITY_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        ctx=ctx,
    )
    if existing is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_run_quality_record_idempotency_reused",
                module=logger.name,
                fields={
                    "normalized_url": request.normalized_url,
                    "outcome": request.summary.outcome,
                    "status": request.summary.status,
                },
            )
        )
        return
    dependencies.record_publisher_inventory_run_quality(request, ctx)
    _record_idempotency_outcome(
        db_path=request.db_path,
        scope=_RUN_QUALITY_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        outcome_payload={
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "summary": asdict(request.summary),
        },
        artifact_references={
            "recommended_route_kind": request.summary.recommended_route_kind,
            "route_kind": request.summary.route_kind,
            "quality_band": request.summary.quality_band,
        },
        ctx=ctx,
    )


def _record_state_if_needed(
    *,
    request: PublisherInventoryStateRecordRequest,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> None:
    checksum = _state_record_checksum(request)
    idempotency_key = _idempotency_key_with_checksum(
        request.normalized_url,
        request.route_kind,
        checksum=checksum,
    )
    existing = _lookup_idempotency_record(
        db_path=request.db_path,
        scope=_STATE_RECORD_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        ctx=ctx,
    )
    if existing is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_state_record_idempotency_reused",
                module=logger.name,
                fields={
                    "normalized_url": request.normalized_url,
                    "route_kind": request.route_kind,
                    "snapshot_sha256": request.snapshot_sha256 or "",
                },
            )
        )
        return
    dependencies.record_publisher_inventory_state(request, ctx)
    _record_idempotency_outcome(
        db_path=request.db_path,
        scope=_STATE_RECORD_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        outcome_payload={
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "route_kind": request.route_kind,
            "route_summary": request.route_summary,
            "snapshot_sha256": request.snapshot_sha256,
        },
        artifact_references={
            "snapshot_drive_file_id": request.snapshot_drive_file_id or "",
            "snapshot_drive_file_name": request.snapshot_drive_file_name or "",
            "last_final_page_url": request.last_final_page_url or "",
        },
        ctx=ctx,
    )


def _record_test_status_if_needed(
    *,
    request: PublisherInventoryTestStatusRecordRequest,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> None:
    checksum = _test_status_record_checksum(request)
    idempotency_key = _idempotency_key_with_checksum(
        request.normalized_url,
        checksum=checksum,
    )
    existing = _lookup_idempotency_record(
        db_path=request.db_path,
        scope=_TEST_STATUS_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        ctx=ctx,
    )
    if existing is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_test_status_record_idempotency_reused",
                module=logger.name,
                fields={
                    "normalized_url": request.normalized_url,
                    "status": request.status,
                },
            )
        )
        return
    dependencies.record_publisher_inventory_test_status(request, ctx)
    _record_idempotency_outcome(
        db_path=request.db_path,
        scope=_TEST_STATUS_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        outcome_payload={
            "schema_version": "1.0",
            "normalized_url": request.normalized_url,
            "status": request.status,
        },
        artifact_references={"status": request.status},
        ctx=ctx,
    )


def _record_recovery_cache_if_needed(
    *,
    request: PublisherInventoryRecoveryCacheRecordRequest,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> None:
    checksum = _recovery_cache_record_checksum(request)
    record = request.record
    idempotency_key = _idempotency_key_with_checksum(
        record.normalized_url,
        record.canonical_url,
        checksum=checksum,
    )
    existing = _lookup_idempotency_record(
        db_path=request.db_path,
        scope=_RECOVERY_CACHE_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        ctx=ctx,
    )
    if existing is not None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_recovery_cache_record_idempotency_reused",
                module=logger.name,
                fields={
                    "normalized_url": record.normalized_url,
                    "canonical_url": record.canonical_url,
                    "verification_class": record.verification_class,
                    "last_outcome": record.last_outcome,
                },
            )
        )
        return
    dependencies.record_publisher_inventory_recovery_cache_record(request, ctx)
    _record_idempotency_outcome(
        db_path=request.db_path,
        scope=_RECOVERY_CACHE_IDEMPOTENCY_SCOPE,
        idempotency_key=idempotency_key,
        input_checksum=checksum,
        outcome_payload={
            "schema_version": "1.0",
            "normalized_url": record.normalized_url,
            "canonical_url": record.canonical_url,
            "verification_class": record.verification_class,
            "recovery_action": record.recovery_action,
            "last_outcome": record.last_outcome,
        },
        artifact_references={
            "canonical_url": record.canonical_url,
            "verification_class": record.verification_class,
            "recovery_action": record.recovery_action,
        },
        ctx=ctx,
    )


def _restore_drive_file(payload: dict[str, object]) -> DriveFile:
    return DriveFile(
        schema_version=str(payload.get("schema_version") or "1.0"),
        file_id=str(payload.get("file_id") or ""),
        name=str(payload.get("name") or ""),
        modified_time=_payload_optional_str(payload, "modified_time"),
        md5_checksum=_payload_optional_str(payload, "md5_checksum"),
        mime_type=_payload_optional_str(payload, "mime_type"),
    )


def _payload_optional_str(payload: dict[str, object], key: str) -> str | None:
    value = payload.get(key)
    if value is None:
        return None
    token = str(value).strip()
    return token or None


def _restore_upload_bytes_response(
    payload: dict[str, object],
) -> DriveUploadBytesResponse:
    file_payload = payload.get("file")
    return DriveUploadBytesResponse(
        schema_version=str(payload.get("schema_version") or "1.0"),
        file=(
            _restore_drive_file(file_payload)
            if isinstance(file_payload, dict)
            else DriveFile(
                schema_version="1.0",
                file_id="",
                name="",
                modified_time=None,
                md5_checksum=None,
                mime_type=None,
            )
        ),
        size=coerce_int(payload.get("size"), 0),
        md5=(str(payload.get("md5")) if payload.get("md5") is not None else None),
    )


def _restore_report_source_record(
    payload: dict[str, object],
) -> ReportSourceDiscoveryRecordResponse:
    return ReportSourceDiscoveryRecordResponse(
        schema_version=str(payload.get("schema_version") or "1.0"),
        record_id=coerce_int(payload.get("record_id"), 0),
        publisher_name=str(payload.get("publisher_name") or ""),
        source_domain=str(payload.get("source_domain") or ""),
        report_name=str(payload.get("report_name") or ""),
        landing_page_url=str(payload.get("landing_page_url") or ""),
        source_page_url=str(payload.get("source_page_url") or ""),
        discovered_at_utc=str(payload.get("discovered_at_utc") or ""),
        discovered_on_page_number=coerce_int(
            payload.get("discovered_on_page_number"), 0
        ),
        created_new=bool(payload.get("created_new")),
    )


def run_publisher_inventory_discovery(
    request: PublisherInventoryDiscoveryRequest,
    *,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies | None = None,
) -> PublisherInventoryDiscoveryResult:
    deps = dependencies or PublisherInventoryDependencies.default()
    normalized_url = normalize_url(request.insights_url)
    deadline_monotonic = time.monotonic() + max(
        float(request.settings.command_time_budget_seconds), 1.0
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_start",
            module=logger.name,
            fields={
                "insights_url": request.insights_url,
                "normalized_url": normalized_url,
                "reports_db": request.reports_db,
                "command_time_budget_seconds": request.settings.command_time_budget_seconds,
            },
        )
    )
    publisher_state = deps.get_publisher_inventory_state(
        PublisherInventoryStateGetRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            normalized_url=normalized_url,
        ),
        ctx,
    )
    if publisher_state is None:
        raise AppError(
            code="publisher_inventory_publisher_not_found",
            message="Publisher insights URL was not found in the reports database",
            retryable=False,
            severity="error",
            context={"normalized_url": normalized_url},
        )
    folder_id = extract_drive_folder_id(publisher_state.google_folder or "")
    if not folder_id:
        _record_discovery_test_status_on_failure(
            request=request,
            normalized_url=normalized_url,
            publisher_state=publisher_state,
            code="publisher_inventory_google_folder_missing",
            ctx=ctx,
            dependencies=deps,
        )
        raise AppError(
            code="publisher_inventory_google_folder_missing",
            message="Publisher discovery requires an existing publisher Drive folder",
            retryable=False,
            severity="error",
            context={
                "publisher_name": publisher_state.publisher_name,
                "normalized_url": normalized_url,
            },
        )
    try:
        (
            previous_snapshot,
            previous_snapshot_file_id,
            previous_snapshot_file_name,
            previous_snapshot_sha256,
        ) = _load_previous_snapshot(
            publisher_state=publisher_state,
            folder_id=folder_id,
            settings=request.settings,
            ctx=ctx,
            dependencies=deps,
        )
        policy = RetryPolicy(
            retries=request.settings.retry_retries,
            base_delay_seconds=request.settings.retry_base_delay_seconds,
            backoff_step_seconds=request.settings.retry_backoff_step_seconds,
            jitter_seconds=request.settings.retry_jitter_seconds,
        )
        route_plan = plan_publisher_inventory_routes(
            PublisherInventoryRoutePlanRequest(
                schema_version="1.0",
                normalized_url=normalized_url,
                force_browser=request.settings.force_browser,
                remembered_route_kind=publisher_state.inventory_route_kind,
                remembered_route_summary=publisher_state.inventory_route_summary,
                remembered_route_trace=publisher_state.inventory_route_trace,
                remembered_scenario_summary=publisher_state.inventory_scenario_summary,
                previous_run_quality_summary=publisher_state.inventory_run_quality_summary,
                route_policy=publisher_state.inventory_route_policy,
                enable_structured_route_reuse=request.settings.enable_structured_route_reuse,
            ),
            ctx,
        )
        discovery_result: PublisherInventoryServiceResponse | None = None
        for step_index, planned_step in enumerate(route_plan.steps):
            try:
                _assert_time_budget_remaining(
                    deadline_monotonic=deadline_monotonic,
                    normalized_url=normalized_url,
                    step_name=planned_step.step_name,
                    ctx=ctx,
                )
                discovery_result = _run_discovery_attempt(
                    request=request,
                    ctx=ctx,
                    policy=policy,
                    dependencies=deps,
                    route_hint=planned_step.route_hint,
                    route_kind_hint=planned_step.route_kind_hint,
                    step_name=planned_step.step_name,
                    deadline_monotonic=deadline_monotonic,
                )
                break
            except AppError as exc:
                if exc.code == "publisher_inventory_browser_pagination_limit":
                    raise
                has_next_route = step_index < len(route_plan.steps) - 1
                should_fallback = (
                    planned_step.fallback_on_retryable_error
                    and has_next_route
                    and (
                        is_retryable_app_error(exc)
                        or (
                            planned_step.route_kind_hint == "http_parse"
                            and exc.code == "publisher_inventory_http_empty"
                        )
                    )
                )
                if (
                    not should_fallback
                ):
                    raise
                fallback_event = (
                    "publisher_inventory_memory_route_failed"
                    if planned_step.uses_memory_route
                    else "publisher_inventory_http_to_browser_fallback"
                )
                logger.info(
                    log_event(
                        ctx,
                        role="orchestrator",
                        event=fallback_event,
                        module=logger.name,
                        fields={
                            "normalized_url": normalized_url,
                            "step_name": planned_step.step_name,
                            "route_kind": planned_step.route_kind_hint or "",
                            "error": exc.message,
                            "code": exc.code,
                        },
                    )
                )
        if discovery_result is None:
            raise AppError(
                code="publisher_inventory_route_plan_exhausted",
                message="Publisher inventory route plan completed without a successful discovery result",
                retryable=False,
                severity="error",
                context={"normalized_url": normalized_url},
            )

        _assert_time_budget_remaining(
            deadline_monotonic=deadline_monotonic,
            normalized_url=normalized_url,
            step_name="publisher_inventory_snapshot_build",
            ctx=ctx,
        )
        build_response = deps.build_publisher_inventory_snapshot(
            PublisherInventoryBuildRequest(
                schema_version="1.0",
                publisher_name=publisher_state.publisher_name,
                insights_url=publisher_state.insights_url,
                normalized_insights_url=normalized_url,
                discovered_at_utc=_utc_now_iso(),
                route_kind=discovery_result.route_kind,
                route_summary=discovery_result.route_summary,
                final_page_url=discovery_result.final_page_url,
                pages=discovery_result.pages,
                candidates=discovery_result.candidates,
                previous_snapshot=previous_snapshot,
            ),
            ctx,
        )
        page_url_by_number = {
            page.page_number: page.page_url for page in build_response.snapshot.pages
        }
        screening_response = deps.screen_publisher_inventory_candidates(
            PublisherInventoryCandidateScreeningRequest(
                schema_version="1.0",
                publisher_name=publisher_state.publisher_name,
                insights_url=publisher_state.insights_url,
                candidates=[
                    PublisherInventoryCandidateScreeningItem(
                        schema_version="1.0",
                        canonical_url=item.canonical_url,
                        title=item.title,
                        discovered_on_page_number=item.discovered_on_page_number,
                        source_page_url=page_url_by_number.get(
                            item.discovered_on_page_number, publisher_state.insights_url
                        ),
                    )
                    for item in build_response.new_items
                ],
                settings=_settings_with_time_budget(
                    request.settings,
                    deadline_monotonic=deadline_monotonic,
                    normalized_url=normalized_url,
                    step_name="publisher_inventory_candidate_screening",
                    ctx=ctx,
                ),
            ),
            ctx,
        )
        approved_item_urls = {
            candidate.canonical_url for candidate in screening_response.approved_items
        }
        approved_items = [
            item
            for item in build_response.new_items
            if item.canonical_url in approved_item_urls
        ]
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_candidate_screening_complete",
                module=logger.name,
                fields={
                    "publisher_name": publisher_state.publisher_name,
                    "raw_new_report_count": len(build_response.new_items),
                    "approved_new_report_count": len(approved_items),
                    "rejected_new_report_count": len(screening_response.rejected_items),
                    "screening_model": screening_response.model,
                    "screening_request_id": screening_response.request_id or "",
                },
            )
        )
        quality_response = deps.qualify_publisher_inventory_candidates(
            PublisherInventoryCandidateQualityRequest(
                schema_version="1.0",
                publisher_name=publisher_state.publisher_name,
                insights_url=publisher_state.insights_url,
                candidates=screening_response.approved_items,
                settings=_settings_with_time_budget(
                    request.settings,
                    deadline_monotonic=deadline_monotonic,
                    normalized_url=normalized_url,
                    step_name="publisher_inventory_candidate_quality",
                    ctx=ctx,
                ),
            ),
            ctx,
        )
        qualified_items = quality_response.approved_items
        qualified_items = _rank_qualified_items_by_resource_quality(
            qualified_items=qualified_items,
            publisher_name=publisher_state.publisher_name,
            reports_db=request.reports_db,
            page_url_by_number=page_url_by_number,
            fallback_source_url=publisher_state.insights_url,
            settings=request.settings,
            ctx=ctx,
            dependencies=deps,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_candidate_quality_complete",
                module=logger.name,
                fields={
                    "publisher_name": publisher_state.publisher_name,
                    "screened_new_report_count": len(approved_items),
                    "qualified_new_report_count": len(qualified_items),
                    "quality_rejected_new_report_count": len(
                        quality_response.rejected_items
                    ),
                },
            )
        )
        deferred_recovery_scheduled_count = _record_deferred_candidate_recovery_cache(
            request=request,
            normalized_url=normalized_url,
            publisher_name=publisher_state.publisher_name,
            quality_response=quality_response,
            ctx=ctx,
            dependencies=deps,
        )
        candidate_snapshot_changed = build_response.snapshot_sha256 != (
            previous_snapshot_sha256 or ""
        )
        coverage_response = deps.validate_publisher_inventory_coverage(
            PublisherInventoryCoverageValidationRequest(
                schema_version="1.0",
                publisher_name=publisher_state.publisher_name,
                normalized_url=normalized_url,
                previous_snapshot_available=previous_snapshot is not None,
                previous_page_count=len(previous_snapshot.pages)
                if previous_snapshot is not None
                else 0,
                previous_report_count=len(previous_snapshot.items)
                if previous_snapshot is not None
                else 0,
                current_page_count=len(build_response.snapshot.pages),
                current_report_count=build_response.current_report_count,
                raw_new_report_count=len(build_response.new_items),
                screened_new_report_count=len(approved_items),
                qualified_new_report_count=len(qualified_items),
                quality_rejection_reasons=[
                    decision.reason for decision in quality_response.decisions
                ],
                candidate_snapshot_changed=candidate_snapshot_changed,
            ),
            ctx,
        )
        if coverage_response.verdict == "unreachable_delta_tolerated":
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_quality_systematic_unreachable_delta_tolerated",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_state.publisher_name,
                        "normalized_url": normalized_url,
                        "screened_new_report_count": len(approved_items),
                        "quality_rejected_new_report_count": len(
                            quality_response.rejected_items
                        ),
                        "previous_snapshot_item_count": len(previous_snapshot.items)
                        if previous_snapshot is not None
                        else 0,
                    },
                )
            )
        elif coverage_response.verdict == "unreachable_delta_failure":
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_quality_systematic_unreachable_failure",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_state.publisher_name,
                        "normalized_url": normalized_url,
                        "screened_new_report_count": len(approved_items),
                        "quality_rejected_new_report_count": len(
                            quality_response.rejected_items
                        ),
                    },
                )
            )
        elif coverage_response.verdict == "no_report_assets":
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_no_report_assets_archive",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_state.publisher_name,
                        "normalized_url": normalized_url,
                        "raw_candidate_count": build_response.current_report_count,
                        "screened_candidate_count": len(approved_items),
                    },
                )
            )
        elif coverage_response.verdict == "undercoverage_regression":
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_undercoverage_regression_detected",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_state.publisher_name,
                        "normalized_url": normalized_url,
                        "previous_report_count": len(previous_snapshot.items)
                        if previous_snapshot is not None
                        else 0,
                        "current_report_count": build_response.current_report_count,
                        "raw_new_report_count": len(build_response.new_items),
                        "qualified_new_report_count": len(qualified_items),
                    },
                )
            )
        elif coverage_response.verdict == "raw_only_delta_rejected":
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_snapshot_guard_rejected_raw_only_delta",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_state.publisher_name,
                        "normalized_url": normalized_url,
                        "raw_new_report_count": len(build_response.new_items),
                        "screened_new_report_count": len(approved_items),
                        "qualified_new_report_count": len(qualified_items),
                        "previous_snapshot_sha256": previous_snapshot_sha256 or "",
                        "candidate_snapshot_sha256": build_response.snapshot_sha256,
                    },
                )
            )
        snapshot_changed = (
            candidate_snapshot_changed and coverage_response.snapshot_allowed
        )
        no_report_assets_detected = coverage_response.no_report_assets_detected
        run_quality_summary = deps.evaluate_publisher_inventory_run_quality(
            PublisherInventoryRunQualityEvaluationRequest(
                schema_version="1.0",
                publisher_name=publisher_state.publisher_name,
                normalized_url=normalized_url,
                route_kind=discovery_result.route_kind,
                used_memory_route=discovery_result.used_route_hint,
                page_count=len(build_response.snapshot.pages),
                raw_candidate_count=len(discovery_result.candidates),
                current_report_count=build_response.current_report_count,
                previous_report_count=build_response.previous_report_count,
                raw_new_report_count=len(build_response.new_items),
                screened_new_report_count=len(approved_items),
                qualified_new_report_count=len(qualified_items),
                snapshot_changed=snapshot_changed,
                coverage_validation=coverage_response,
                candidate_provenance_counts=_candidate_provenance_counts(
                    discovery_result.candidates
                ),
            ),
            ctx,
        )
        if discovery_result.scenario_summary is not None:
            run_quality_summary = replace(
                run_quality_summary,
                scenario_class=discovery_result.scenario_summary.scenario_class,
            )
        _log_rollout_guardrails(
            request=request,
            normalized_url=normalized_url,
            publisher_name=publisher_state.publisher_name,
            discovery_result=discovery_result,
            run_quality_summary=run_quality_summary,
            coverage_response=coverage_response,
            raw_new_report_count=len(build_response.new_items),
            screened_new_report_count=len(approved_items),
            qualified_new_report_count=len(qualified_items),
            quality_rejected_new_report_count=len(quality_response.rejected_items),
            deferred_recovery_scheduled_count=deferred_recovery_scheduled_count,
            ctx=ctx,
        )
        _assert_time_budget_remaining(
            deadline_monotonic=deadline_monotonic,
            normalized_url=normalized_url,
            step_name="publisher_inventory_run_quality_record",
            ctx=ctx,
        )
        run_quality_record_request = PublisherInventoryRunQualityRecordRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            normalized_url=normalized_url,
            summary=run_quality_summary,
        )
        run_with_retry(
            step_name="publisher_inventory_run_quality_record",
            operation=lambda: _record_run_quality_if_needed(
                request=run_quality_record_request,
                ctx=ctx,
                dependencies=deps,
            ),
            ctx=ctx,
            logger=logger,
            module_name=logger.name,
            policy=policy,
            retry_event="publisher_inventory_run_quality_record_retry",
            failure_event="publisher_inventory_run_quality_record_failed",
        )
        if coverage_response.should_raise_error:
            raise AppError(
                code=str(
                    coverage_response.error_code
                    or "publisher_inventory_coverage_invalid"
                ),
                message=str(
                    coverage_response.error_message
                    or coverage_response.reason
                    or "Publisher inventory coverage validation failed"
                ),
                retryable=False,
                severity="error",
                context={
                    "publisher_name": publisher_state.publisher_name,
                    "normalized_url": normalized_url,
                    "coverage_verdict": coverage_response.verdict,
                },
            )
        snapshot_drive_file_id = previous_snapshot_file_id
        snapshot_drive_file_name = previous_snapshot_file_name
        snapshot_sha256 = previous_snapshot_sha256
        if snapshot_changed:
            _assert_time_budget_remaining(
                deadline_monotonic=deadline_monotonic,
                normalized_url=normalized_url,
                step_name="publisher_inventory_snapshot_upload",
                ctx=ctx,
            )
            snapshot_upload_request = DriveUploadBytesRequest(
                schema_version="1.0",
                folder_id=folder_id,
                service_account_path=request.settings.google_sa_path,
                auth_mode=request.settings.drive_auth_mode,
                oauth_client_path=request.settings.google_oauth_client_path,
                oauth_token_path=request.settings.google_oauth_token_path,
                file_name=_snapshot_file_name(),
                content=build_response.snapshot_json.encode("utf-8"),
                mime_type="application/json",
                supports_all_drives=True,
            )
            snapshot_upload_key = f"{normalized_url}:{build_response.snapshot_sha256}"
            snapshot_upload_checksum = sha256_json(
                {
                    "schema_version": "1.0",
                    "folder_id": snapshot_upload_request.folder_id,
                    "mime_type": snapshot_upload_request.mime_type,
                    "snapshot_sha256": build_response.snapshot_sha256,
                }
            )
            existing_snapshot_upload = _lookup_idempotency_record(
                db_path=request.reports_db,
                scope=_SNAPSHOT_UPLOAD_IDEMPOTENCY_SCOPE,
                idempotency_key=snapshot_upload_key,
                input_checksum=snapshot_upload_checksum,
                ctx=ctx,
            )
            if existing_snapshot_upload is not None:
                upload_response = _restore_upload_bytes_response(
                    dict(existing_snapshot_upload.outcome_payload or {})
                )
                logger.info(
                    log_event(
                        ctx,
                        role="orchestrator",
                        event="publisher_inventory_snapshot_upload_idempotency_reused",
                        module=logger.name,
                        fields={
                            "normalized_url": normalized_url,
                            "snapshot_drive_file_id": upload_response.file.file_id,
                            "snapshot_drive_file_name": upload_response.file.name or "",
                            "snapshot_sha256": build_response.snapshot_sha256,
                        },
                    )
                )
            else:
                upload_response = run_with_retry(
                    step_name="publisher_inventory_snapshot_upload",
                    operation=lambda: deps.upload_bytes(
                        snapshot_upload_request,
                        ctx,
                    ),
                    ctx=ctx,
                    logger=logger,
                    module_name=logger.name,
                    policy=policy,
                    retry_event="publisher_inventory_snapshot_upload_retry",
                    failure_event="publisher_inventory_snapshot_upload_failed",
                )
                _record_idempotency_outcome(
                    db_path=request.reports_db,
                    scope=_SNAPSHOT_UPLOAD_IDEMPOTENCY_SCOPE,
                    idempotency_key=snapshot_upload_key,
                    input_checksum=snapshot_upload_checksum,
                    outcome_payload=asdict(upload_response),
                    artifact_references={
                        "folder_id": snapshot_upload_request.folder_id,
                        "snapshot_drive_file_id": upload_response.file.file_id,
                        "snapshot_drive_file_name": upload_response.file.name or "",
                        "snapshot_sha256": build_response.snapshot_sha256,
                    },
                    ctx=ctx,
                )
            snapshot_drive_file_id = upload_response.file.file_id
            snapshot_drive_file_name = upload_response.file.name
            snapshot_sha256 = build_response.snapshot_sha256
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_snapshot_uploaded",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "snapshot_drive_file_id": snapshot_drive_file_id,
                        "snapshot_drive_file_name": snapshot_drive_file_name or "",
                        "snapshot_sha256": snapshot_sha256,
                    },
                )
            )
        for item in qualified_items:
            _assert_time_budget_remaining(
                deadline_monotonic=deadline_monotonic,
                normalized_url=normalized_url,
                step_name="publisher_inventory_report_source_record",
                ctx=ctx,
            )
            source_record_request = ReportSourceDiscoveryRecordRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                publisher_name=publisher_state.publisher_name,
                source_domain=_source_domain_for_url(item.canonical_url),
                report_name=item.title,
                landing_page_url=item.canonical_url,
                source_page_url=page_url_by_number.get(
                    item.discovered_on_page_number, publisher_state.insights_url
                ),
                discovered_at_utc=build_response.snapshot.discovered_at_utc,
                discovered_on_page_number=item.discovered_on_page_number,
            )
            source_record_key = f"{normalized_url}:{item.canonical_url}"
            source_record_checksum = sha256_json(
                {
                    "schema_version": "1.0",
                    "publisher_name": source_record_request.publisher_name,
                    "source_domain": source_record_request.source_domain,
                    "report_name": source_record_request.report_name,
                    "landing_page_url": source_record_request.landing_page_url,
                    "source_page_url": source_record_request.source_page_url,
                    "discovered_on_page_number": source_record_request.discovered_on_page_number,
                }
            )
            existing_source_record = _lookup_idempotency_record(
                db_path=request.reports_db,
                scope=_REPORT_SOURCE_RECORD_IDEMPOTENCY_SCOPE,
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
                        event="publisher_inventory_report_source_record_idempotency_reused",
                        module=logger.name,
                        fields={
                            "publisher_name": source_record.publisher_name,
                            "landing_page_url": source_record.landing_page_url,
                            "record_id": source_record.record_id,
                        },
                    )
                )
            else:
                source_record = run_with_retry(
                    step_name="publisher_inventory_report_source_record",
                    operation=lambda: deps.record_discovered_report_source(
                        source_record_request,
                        ctx,
                    ),
                    ctx=ctx,
                    logger=logger,
                    module_name=logger.name,
                    policy=policy,
                    retry_event="publisher_inventory_report_source_record_retry",
                    failure_event="publisher_inventory_report_source_record_failed",
                )
                _record_idempotency_outcome(
                    db_path=request.reports_db,
                    scope=_REPORT_SOURCE_RECORD_IDEMPOTENCY_SCOPE,
                    idempotency_key=source_record_key,
                    input_checksum=source_record_checksum,
                    outcome_payload=asdict(source_record),
                    artifact_references={
                        "record_id": source_record.record_id,
                        "landing_page_url": source_record.landing_page_url,
                        "source_page_url": source_record.source_page_url,
                    },
                    ctx=ctx,
                )
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_report_source_recorded",
                    module=logger.name,
                    fields={
                        "record_id": source_record.record_id,
                        "publisher_name": source_record.publisher_name,
                        "report_name": source_record.report_name,
                        "landing_page_url": source_record.landing_page_url,
                        "source_page_url": source_record.source_page_url,
                        "discovered_on_page_number": source_record.discovered_on_page_number,
                        "created_new": source_record.created_new,
                    },
                )
            )
        _record_state_if_needed(
            request=PublisherInventoryStateRecordRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                normalized_url=normalized_url,
                source_url=publisher_state.insights_url,
                route_kind=discovery_result.route_kind,
                route_summary=discovery_result.route_summary,
                route_trace=discovery_result.route_trace,
                scenario_summary=discovery_result.scenario_summary,
                last_final_page_url=discovery_result.final_page_url,
                snapshot_drive_file_id=snapshot_drive_file_id,
                snapshot_drive_file_name=snapshot_drive_file_name,
                snapshot_sha256=snapshot_sha256 or build_response.snapshot_sha256,
            ),
            ctx=ctx,
            dependencies=deps,
        )
        _record_test_status_if_needed(
            request=PublisherInventoryTestStatusRecordRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                normalized_url=normalized_url,
                status=(
                    "passed:no_report_assets" if no_report_assets_detected else "passed"
                ),
            ),
            ctx=ctx,
            dependencies=deps,
        )
        response = PublisherInventoryDiscoveryResult(
            schema_version="1.0",
            publisher_name=publisher_state.publisher_name,
            insights_url=publisher_state.insights_url,
            normalized_insights_url=normalized_url,
            new_report_urls=[
                PublisherInventoryDiffItem(
                    schema_version="1.0",
                    canonical_url=item.canonical_url,
                    title=item.title,
                    discovered_on_page_number=item.discovered_on_page_number,
                )
                for item in qualified_items
            ],
            current_report_count=build_response.current_report_count,
            previous_report_count=build_response.previous_report_count,
            used_memory_route=discovery_result.used_route_hint,
            snapshot_changed=snapshot_changed,
            run_quality_summary=run_quality_summary,
            current_candidates=build_response.current_candidates,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_complete",
                module=logger.name,
                fields={
                    "publisher_name": response.publisher_name,
                    "normalized_url": response.normalized_insights_url,
                    "current_report_count": response.current_report_count,
                    "previous_report_count": response.previous_report_count,
                    "new_report_count": len(response.new_report_urls),
                    "current_candidate_count": len(response.current_candidates),
                    "used_memory_route": response.used_memory_route,
                    "snapshot_changed": response.snapshot_changed,
                    "run_quality_outcome": response.run_quality_summary.outcome,
                    "run_quality_band": response.run_quality_summary.quality_band,
                },
            )
        )
        return response
    except AppError as exc:
        _record_discovery_test_status_on_failure(
            request=request,
            normalized_url=normalized_url,
            publisher_state=publisher_state,
            code=exc.code,
            ctx=ctx,
            dependencies=deps,
        )
        raise


def _record_discovery_test_status_on_failure(
    *,
    request: PublisherInventoryDiscoveryRequest,
    normalized_url: str,
    publisher_state: PublisherInventoryStateResponse,
    code: str,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> None:
    status = _discovery_test_status_for_error_code(code)
    try:
        _record_test_status_if_needed(
            request=PublisherInventoryTestStatusRecordRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                normalized_url=normalized_url,
                status=status,
            ),
            ctx=ctx,
            dependencies=dependencies,
        )
    except Exception as exc:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_test_status_record_failed",
                module=logger.name,
                fields={
                    "publisher_name": publisher_state.publisher_name,
                    "normalized_url": normalized_url,
                    "status": status,
                    "error": str(exc),
                },
            )
        )


def _discovery_test_status_for_error_code(code: str) -> str:
    normalized = str(code or "").strip()
    if not normalized:
        return "failed:unknown"
    if normalized == "publisher_inventory_browser_pagination_limit":
        return f"bounded:{normalized}"
    return f"failed:{normalized}"


def _rank_qualified_items_by_resource_quality(
    *,
    qualified_items,
    publisher_name: str,
    reports_db: str,
    page_url_by_number: dict[int, str],
    fallback_source_url: str,
    settings,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
):
    if not qualified_items or not settings.resource_quality_ranking_enabled:
        return qualified_items
    source_urls = [
        page_url_by_number.get(item.discovered_on_page_number, fallback_source_url)
        for item in qualified_items
    ]
    history = dependencies.list_report_source_quality_history(
        ReportSourceQualityHistoryRequest(
            schema_version="1.0",
            db_path=reports_db,
            publisher_name=publisher_name,
            limit=max(
                settings.resource_quality_score_window_size
                * max(1, len(set(source_urls))),
                settings.resource_quality_score_window_size,
            ),
        ),
        ctx,
    )
    ranking = dependencies.rank_publisher_resources(
        PublisherResourceRankingRequest(
            schema_version="1.0",
            publisher_name=publisher_name,
            candidate_source_page_urls=source_urls,
            history_items=history.items,
            policy=PublisherResourceRankingPolicy(
                schema_version="1.0",
                score_window_size=settings.resource_quality_score_window_size,
                min_sample_size=settings.resource_quality_min_sample_size,
                consistency_weight=settings.resource_quality_consistency_weight,
                average_score_weight=settings.resource_quality_average_weight,
                confidence_weight=settings.resource_quality_confidence_weight,
                low_score_demotion_threshold=(
                    settings.resource_quality_low_score_demotion_threshold
                ),
            ),
        ),
        ctx,
    )
    rank_by_url = {item.resource_url: index for index, item in enumerate(ranking.items)}
    score_by_url = {item.resource_url: item for item in ranking.items}

    def source_url_for_item(item) -> str:
        source_url = page_url_by_number.get(
            item.discovered_on_page_number, fallback_source_url
        )
        return normalize_url(source_url) or source_url

    def sort_key(item) -> tuple[int, int, str]:
        normalized_source_url = source_url_for_item(item)
        return (
            rank_by_url.get(normalized_source_url, len(rank_by_url)),
            item.discovered_on_page_number,
            item.canonical_url,
        )

    ranked_items = sorted(qualified_items, key=sort_key)
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_resource_quality_ranking_applied",
            module=logger.name,
            fields={
                "publisher_name": publisher_name,
                "history_sample_count": len(history.items),
                "score_window_size": settings.resource_quality_score_window_size,
                "min_sample_size": settings.resource_quality_min_sample_size,
                "ranked_resource_count": len(ranking.items),
                "resource_rankings": [
                    {
                        "resource_url": item.resource_url,
                        "sample_size": item.sample_size,
                        "confidence": item.confidence,
                        "rank_score": item.rank_score,
                        "demotion_reason": item.demotion_reason,
                    }
                    for item in ranking.items
                ],
                "ordered_candidate_urls": [item.canonical_url for item in ranked_items],
                "candidate_resource_scores": {
                    item.canonical_url: score_by_url[
                        source_url_for_item(item)
                    ].rank_score
                    if source_url_for_item(item) in score_by_url
                    else 0.0
                    for item in ranked_items
                },
            },
        )
    )
    return ranked_items


def _candidate_provenance_counts(
    candidates,
) -> dict[str, int]:
    counts: dict[str, int] = {}
    for candidate in candidates:
        provenance = str(getattr(candidate, "provenance", "") or "unknown").strip()
        key = provenance or "unknown"
        counts[key] = counts.get(key, 0) + 1
    return counts


def _record_deferred_candidate_recovery_cache(
    *,
    request: PublisherInventoryDiscoveryRequest,
    normalized_url: str,
    publisher_name: str,
    quality_response: PublisherInventoryCandidateQualityResponse,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> int:
    scheduled_count = 0
    for decision in quality_response.decisions:
        recipe = decision.recovery_recipe
        if recipe is None:
            continue
        existing = dependencies.get_publisher_inventory_recovery_cache_record(
            PublisherInventoryRecoveryCacheGetRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                normalized_url=normalized_url,
                canonical_url=decision.canonical_url,
            ),
            ctx,
        )
        if (
            existing is not None
            and existing.verification_class == recipe.verification_class
            and existing.recovery_action == recipe.recovery_action
            and existing.last_outcome in {"scheduled", "recovered"}
        ):
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_candidate_recovery_cache_reused",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_name,
                        "normalized_url": normalized_url,
                        "canonical_url": decision.canonical_url,
                        "verification_class": existing.verification_class,
                        "last_outcome": existing.last_outcome,
                    },
                )
            )
            continue
        last_outcome = (
            "scheduled"
            if request.settings.enable_deferred_candidate_recovery
            else "skipped"
        )
        if last_outcome == "scheduled":
            scheduled_count += 1
        _record_recovery_cache_if_needed(
            request=PublisherInventoryRecoveryCacheRecordRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                record=PublisherInventoryRecoveryRecord(
                    schema_version="1.0",
                    normalized_url=normalized_url,
                    canonical_url=decision.canonical_url,
                    source_surface_class=decision.source_surface_class,
                    verification_class=recipe.verification_class,
                    recovery_action=recipe.recovery_action,
                    last_outcome=last_outcome,
                    last_http_status=None,
                    last_error_marker=decision.reason,
                    updated_at_utc=_utc_now_iso(),
                ),
            ),
            ctx=ctx,
            dependencies=dependencies,
        )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_candidate_recovery_cache_recorded",
                module=logger.name,
                fields={
                    "publisher_name": publisher_name,
                    "normalized_url": normalized_url,
                    "canonical_url": decision.canonical_url,
                    "verification_class": recipe.verification_class,
                    "recovery_action": recipe.recovery_action,
                    "last_outcome": last_outcome,
                },
            )
        )
    return scheduled_count


def _log_rollout_guardrails(
    *,
    request: PublisherInventoryDiscoveryRequest,
    normalized_url: str,
    publisher_name: str,
    discovery_result: PublisherInventoryServiceResponse,
    run_quality_summary,
    coverage_response: PublisherInventoryCoverageValidationResponse,
    raw_new_report_count: int,
    screened_new_report_count: int,
    qualified_new_report_count: int,
    quality_rejected_new_report_count: int,
    deferred_recovery_scheduled_count: int,
    ctx: RunContext,
) -> None:
    precision_guardrail_passed = (
        0
        <= qualified_new_report_count
        <= screened_new_report_count
        <= raw_new_report_count
    )
    coverage_guardrail_passed = coverage_response.verdict not in {
        "undercoverage_regression",
        "unreachable_delta_failure",
    }
    kpi_guardrail_status = (
        "pass"
        if precision_guardrail_passed
        and coverage_guardrail_passed
        and not run_quality_summary.requires_review
        else "review_required"
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_rollout_guardrails_evaluated",
            module=logger.name,
            fields={
                "publisher_name": publisher_name,
                "normalized_url": normalized_url,
                "rollout_flags": {
                    "enable_deferred_candidate_recovery": (
                        request.settings.enable_deferred_candidate_recovery
                    ),
                    "enable_structured_route_reuse": (
                        request.settings.enable_structured_route_reuse
                    ),
                    "enable_preflight_classifier_and_direct_detail": (
                        request.settings.enable_preflight_classifier_and_direct_detail
                    ),
                },
                "canary_kpi_set": {
                    "coverage_verdict": coverage_response.verdict,
                    "run_quality_band": run_quality_summary.quality_band,
                    "raw_new_report_count": raw_new_report_count,
                    "screened_new_report_count": screened_new_report_count,
                    "qualified_new_report_count": qualified_new_report_count,
                    "quality_rejected_new_report_count": quality_rejected_new_report_count,
                    "candidate_provenance_counts": (
                        run_quality_summary.candidate_provenance_counts
                    ),
                },
                "scenario_class": (
                    discovery_result.scenario_summary.scenario_class
                    if discovery_result.scenario_summary is not None
                    else ""
                ),
                "used_memory_route": discovery_result.used_route_hint,
                "deferred_recovery_scheduled_count": deferred_recovery_scheduled_count,
                "precision_guardrail_passed": precision_guardrail_passed,
                "coverage_guardrail_passed": coverage_guardrail_passed,
                "run_quality_requires_review": run_quality_summary.requires_review,
                "kpi_guardrail_status": kpi_guardrail_status,
                "rollback_condition": (
                    "disable rollout flags or force browser review when status is review_required"
                ),
            },
        )
    )


def _run_discovery_attempt(
    *,
    request: PublisherInventoryDiscoveryRequest,
    ctx: RunContext,
    policy: RetryPolicy,
    dependencies: PublisherInventoryDependencies,
    route_hint: str | None,
    route_kind_hint: str | None,
    step_name: str,
    deadline_monotonic: float,
) -> PublisherInventoryServiceResponse:
    return run_with_retry(
        step_name=step_name,
        operation=lambda: dependencies.discover_publisher_inventory(
            PublisherInventoryServiceRequest(
                schema_version="1.0",
                insights_url=request.insights_url,
                settings=_settings_with_time_budget(
                    request.settings,
                    deadline_monotonic=deadline_monotonic,
                    normalized_url=normalize_url(request.insights_url),
                    step_name=step_name,
                    ctx=ctx,
                ),
                route_hint=route_hint,
                route_kind_hint=route_kind_hint,
            ),
            ctx,
        ),
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=policy,
        retry_event="publisher_inventory_discovery_retry",
        failure_event="publisher_inventory_discovery_failed",
    )


def _remaining_time_budget_seconds(*, deadline_monotonic: float) -> float:
    return max(0.0, float(deadline_monotonic) - time.monotonic())


def _assert_time_budget_remaining(
    *,
    deadline_monotonic: float,
    normalized_url: str,
    step_name: str,
    ctx: RunContext,
    minimum_seconds: float = 1.0,
) -> float:
    remaining_seconds = _remaining_time_budget_seconds(
        deadline_monotonic=deadline_monotonic
    )
    if remaining_seconds >= minimum_seconds:
        return remaining_seconds
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_time_budget_exceeded",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "step_name": step_name,
                "remaining_seconds": remaining_seconds,
                "minimum_seconds": minimum_seconds,
            },
        )
    )
    raise AppError(
        code="publisher_inventory_time_budget_exceeded",
        message="Publisher inventory discovery exceeded the configured per-publisher time budget",
        retryable=False,
        severity="error",
        context={
            "normalized_url": normalized_url,
            "step_name": step_name,
            "remaining_seconds": remaining_seconds,
        },
    )


def _settings_with_time_budget(
    settings,
    *,
    deadline_monotonic: float,
    normalized_url: str,
    step_name: str,
    ctx: RunContext,
):
    remaining_seconds = _assert_time_budget_remaining(
        deadline_monotonic=deadline_monotonic,
        normalized_url=normalized_url,
        step_name=step_name,
        ctx=ctx,
    )
    return replace(
        settings,
        timeout_seconds=max(1.0, min(settings.timeout_seconds, remaining_seconds)),
        candidate_screening_timeout_seconds=max(
            1.0,
            min(settings.candidate_screening_timeout_seconds, remaining_seconds),
        ),
        candidate_quality_check_timeout_seconds=max(
            1.0,
            min(settings.candidate_quality_check_timeout_seconds, remaining_seconds),
        ),
    )


def _load_previous_snapshot(
    *,
    publisher_state: PublisherInventoryStateResponse,
    folder_id: str,
    settings,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> tuple[PublisherInventorySnapshot | None, str | None, str | None, str | None]:
    file_id = publisher_state.inventory_snapshot_drive_file_id
    file_name = publisher_state.inventory_snapshot_drive_file_name
    snapshot_sha256 = publisher_state.inventory_snapshot_sha256
    candidates: list[tuple[str, str | None, str | None]] = []
    if file_id:
        candidates.append((file_id, file_name, snapshot_sha256))
    if not file_id:
        listed = dependencies.list_files_in_folder(
            DriveFolderFileListRequest(
                schema_version="1.0",
                folder_id=folder_id,
                service_account_path=settings.google_sa_path,
                auth_mode=settings.drive_auth_mode,
                oauth_client_path=settings.google_oauth_client_path,
                oauth_token_path=settings.google_oauth_token_path,
                name_prefix=_SNAPSHOT_PREFIX,
                order_by="modifiedTime desc",
                limit=_SNAPSHOT_LOOKBACK_LIMIT,
                supports_all_drives=True,
                include_items_from_all_drives=True,
            ),
            ctx,
        )
        candidates.extend((file.file_id, file.name, None) for file in listed.files)
    if not candidates:
        return None, None, None, None

    for candidate_file_id, candidate_file_name, candidate_sha256 in candidates:
        download_response = dependencies.download_pdf(
            DriveDownloadRequest(
                schema_version="1.0",
                file=DriveFile(
                    schema_version="1.0",
                    file_id=candidate_file_id,
                    name=candidate_file_name,
                    modified_time=None,
                    md5_checksum=None,
                    mime_type="application/json",
                ),
                service_account_path=settings.google_sa_path,
                auth_mode=settings.drive_auth_mode,
                oauth_client_path=settings.google_oauth_client_path,
                oauth_token_path=settings.google_oauth_token_path,
            ),
            ctx,
        )
        snapshot_payload = download_response.content.decode("utf-8")
        resolved_sha256 = (
            candidate_sha256
            or hashlib.sha256(snapshot_payload.encode("utf-8")).hexdigest()
        )
        try:
            snapshot = dependencies.parse_publisher_inventory_snapshot(
                snapshot_payload,
                f"drive:{candidate_file_id}",
                ctx,
            )
        except AppError as exc:
            if exc.code != "publisher_inventory_snapshot_invalid_payload":
                raise
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_previous_snapshot_skipped",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_state.publisher_name,
                        "snapshot_drive_file_id": candidate_file_id,
                        "snapshot_drive_file_name": candidate_file_name or "",
                        "snapshot_sha256": resolved_sha256,
                        "code": exc.code,
                    },
                )
            )
            continue
        if normalize_url(snapshot.normalized_insights_url) != normalize_url(
            publisher_state.normalized_url
        ):
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_previous_snapshot_skipped",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_state.publisher_name,
                        "snapshot_drive_file_id": candidate_file_id,
                        "snapshot_drive_file_name": candidate_file_name or "",
                        "snapshot_sha256": resolved_sha256,
                        "code": "publisher_inventory_snapshot_publisher_mismatch",
                        "snapshot_normalized_url": snapshot.normalized_insights_url,
                        "expected_normalized_url": publisher_state.normalized_url,
                    },
                )
            )
            continue
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="publisher_inventory_previous_snapshot_loaded",
                module=logger.name,
                fields={
                    "publisher_name": publisher_state.publisher_name,
                    "snapshot_drive_file_id": candidate_file_id,
                    "snapshot_drive_file_name": candidate_file_name or "",
                    "snapshot_sha256": resolved_sha256,
                    "item_count": len(snapshot.items),
                },
            )
        )
        return snapshot, candidate_file_id, candidate_file_name, resolved_sha256
    return None, None, None, None


def _snapshot_file_name() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{_SNAPSHOT_PREFIX}{timestamp}.json"


def _utc_now_iso() -> str:
    return (
        datetime.now(timezone.utc)
        .replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z")
    )


def _source_domain_for_url(url: str) -> str:
    return str(urlsplit(str(url).strip()).hostname or "").strip().lower()
