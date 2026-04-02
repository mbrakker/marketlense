from __future__ import annotations

import hashlib
import logging
import time
from dataclasses import dataclass, replace
from datetime import datetime, timezone
from typing import Callable, Optional
from urllib.parse import urlsplit

from src.contracts.drive import (
    DriveDownloadRequest,
    DriveFile,
    DriveFolderFileListRequest,
    DriveFolderFileListResponse,
    DriveUploadBytesRequest,
    DriveUploadBytesResponse,
)
from src.contracts.publisher_inventory import (
    PublisherInventoryBuildRequest,
    PublisherInventoryBuildResponse,
    PublisherInventoryCandidateQualityRequest,
    PublisherInventoryCandidateQualityResponse,
    PublisherInventoryCandidateScreeningItem,
    PublisherInventoryCandidateScreeningRequest,
    PublisherInventoryCandidateScreeningResponse,
    PublisherInventoryDiscoveryRequest,
    PublisherInventoryDiscoveryResult,
    PublisherInventoryDiffItem,
    PublisherInventoryServiceRequest,
    PublisherInventoryServiceResponse,
    PublisherInventorySnapshot,
)
from src.contracts.report_store import (
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
from src.generators.publisher_inventory_candidate_screening_generator import (
    screen_publisher_inventory_candidates,
)
from src.generators.publisher_inventory_candidate_quality_generator import (
    qualify_publisher_inventory_candidates,
)
from src.orchestrators.retry_orchestrator import RetryPolicy, run_with_retry
from src.services.drive_service import download_pdf, list_files_in_folder, upload_bytes
from src.services.publisher_inventory_service import discover_publisher_inventory
from src.services.report_store_service import (
    get_publisher_inventory_state,
    record_discovered_report_source,
    record_publisher_inventory_state,
    record_publisher_inventory_test_status,
)
from src.utils.drive_utils import extract_drive_folder_id
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.publisher_inventory_orchestrator")

_SNAPSHOT_PREFIX = "publisher_inventory_snapshot__"


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
    list_files_in_folder: Callable[
        [DriveFolderFileListRequest, RunContext],
        DriveFolderFileListResponse,
    ]
    download_pdf: Callable[[DriveDownloadRequest, RunContext], object]
    upload_bytes: Callable[[DriveUploadBytesRequest, RunContext], DriveUploadBytesResponse]

    @classmethod
    def default(cls) -> "PublisherInventoryDependencies":
        return cls(
            discover_publisher_inventory=discover_publisher_inventory,
            build_publisher_inventory_snapshot=build_publisher_inventory_snapshot,
            parse_publisher_inventory_snapshot=lambda snapshot_json, source, ctx: (
                parse_publisher_inventory_snapshot(snapshot_json, source=source, ctx=ctx)
            ),
            screen_publisher_inventory_candidates=screen_publisher_inventory_candidates,
            qualify_publisher_inventory_candidates=qualify_publisher_inventory_candidates,
            get_publisher_inventory_state=get_publisher_inventory_state,
            record_publisher_inventory_state=record_publisher_inventory_state,
            record_publisher_inventory_test_status=record_publisher_inventory_test_status,
            record_discovered_report_source=record_discovered_report_source,
            list_files_in_folder=list_files_in_folder,
            download_pdf=download_pdf,
            upload_bytes=upload_bytes,
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
        previous_snapshot, previous_snapshot_file_id, previous_snapshot_file_name, previous_snapshot_sha256 = _load_previous_snapshot(
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
        discovery_result: PublisherInventoryServiceResponse | None = None
        if publisher_state.inventory_route_summary:
            try:
                _assert_time_budget_remaining(
                    deadline_monotonic=deadline_monotonic,
                    normalized_url=normalized_url,
                    step_name="publisher_inventory_discovery_with_memory_route",
                    ctx=ctx,
                )
                discovery_result = _run_discovery_attempt(
                    request=request,
                    ctx=ctx,
                    policy=policy,
                    dependencies=deps,
                    route_hint=publisher_state.inventory_route_summary,
                    route_kind_hint=publisher_state.inventory_route_kind,
                    step_name="publisher_inventory_discovery_with_memory_route",
                    deadline_monotonic=deadline_monotonic,
                )
            except AppError as exc:
                if exc.code == "publisher_inventory_browser_pagination_limit":
                    raise
                logger.info(
                    log_event(
                        ctx,
                        role="orchestrator",
                        event="publisher_inventory_memory_route_failed",
                        module=logger.name,
                        fields={
                            "normalized_url": normalized_url,
                            "route_kind": publisher_state.inventory_route_kind or "",
                            "error": str(exc),
                        },
                    )
                )
            except Exception as exc:
                logger.info(
                    log_event(
                        ctx,
                        role="orchestrator",
                        event="publisher_inventory_memory_route_failed",
                        module=logger.name,
                        fields={
                            "normalized_url": normalized_url,
                            "route_kind": publisher_state.inventory_route_kind or "",
                            "error": str(exc),
                        },
                    )
                )
        if discovery_result is None:
            if request.settings.force_browser:
                _assert_time_budget_remaining(
                    deadline_monotonic=deadline_monotonic,
                    normalized_url=normalized_url,
                    step_name="publisher_inventory_discovery_browser",
                    ctx=ctx,
                )
                discovery_result = _run_discovery_attempt(
                    request=request,
                    ctx=ctx,
                    policy=policy,
                    dependencies=deps,
                    route_hint=None,
                    route_kind_hint="browser_render",
                    step_name="publisher_inventory_discovery_browser",
                    deadline_monotonic=deadline_monotonic,
                )
            else:
                try:
                    _assert_time_budget_remaining(
                        deadline_monotonic=deadline_monotonic,
                        normalized_url=normalized_url,
                        step_name="publisher_inventory_discovery_http",
                        ctx=ctx,
                    )
                    discovery_result = _run_discovery_attempt(
                        request=request,
                        ctx=ctx,
                        policy=policy,
                        dependencies=deps,
                        route_hint=None,
                        route_kind_hint="http_parse",
                        step_name="publisher_inventory_discovery_http",
                        deadline_monotonic=deadline_monotonic,
                    )
                except AppError as exc:
                    if exc.code == "publisher_inventory_time_budget_exceeded":
                        raise
                    logger.info(
                        log_event(
                            ctx,
                            role="orchestrator",
                            event="publisher_inventory_http_to_browser_fallback",
                            module=logger.name,
                            fields={
                                "normalized_url": normalized_url,
                                "error": exc.message,
                                "code": exc.code,
                            },
                        )
                    )
                    _assert_time_budget_remaining(
                        deadline_monotonic=deadline_monotonic,
                        normalized_url=normalized_url,
                        step_name="publisher_inventory_discovery_browser",
                        ctx=ctx,
                    )
                    discovery_result = _run_discovery_attempt(
                        request=request,
                        ctx=ctx,
                        policy=policy,
                        dependencies=deps,
                        route_hint=None,
                        route_kind_hint="browser_render",
                        step_name="publisher_inventory_discovery_browser",
                        deadline_monotonic=deadline_monotonic,
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
        if _is_systematic_landing_page_failure(
            screened_candidate_count=len(approved_items),
            quality_response=quality_response,
        ):
            if previous_snapshot is not None:
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
                            "previous_snapshot_item_count": len(previous_snapshot.items),
                        },
                    )
                )
            else:
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
                raise AppError(
                    code="publisher_inventory_candidate_quality_unreachable_archive",
                    message="Landing-page quality verification rejected all screened candidates as unreachable",
                    retryable=False,
                    severity="error",
                    context={
                        "publisher_name": publisher_state.publisher_name,
                        "normalized_url": normalized_url,
                        "screened_new_report_count": len(approved_items),
                    },
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
        no_report_assets_detected = _is_no_report_assets_archive(
            previous_snapshot_available=previous_snapshot is not None,
            raw_candidate_count=build_response.current_report_count,
            screened_candidate_count=len(approved_items),
            qualified_candidate_count=len(qualified_items),
            quality_response=quality_response,
        )
        if no_report_assets_detected:
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
        if _is_undercoverage_regression(
            previous_snapshot=previous_snapshot,
            current_page_count=len(build_response.snapshot.pages),
            current_report_count=build_response.current_report_count,
            raw_new_report_count=len(build_response.new_items),
            qualified_candidate_count=len(qualified_items),
        ):
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="publisher_inventory_undercoverage_regression_detected",
                    module=logger.name,
                    fields={
                        "publisher_name": publisher_state.publisher_name,
                        "normalized_url": normalized_url,
                        "previous_report_count": len(previous_snapshot.items),
                        "current_report_count": build_response.current_report_count,
                        "raw_new_report_count": len(build_response.new_items),
                        "qualified_new_report_count": len(qualified_items),
                    },
                )
            )
            raise AppError(
                code="publisher_inventory_browser_incomplete",
                message="Discovery returned a materially smaller inventory without any new qualified report assets",
                retryable=False,
                severity="error",
                context={
                    "publisher_name": publisher_state.publisher_name,
                    "normalized_url": normalized_url,
                    "previous_report_count": len(previous_snapshot.items),
                    "current_report_count": build_response.current_report_count,
                },
            )
        snapshot_changed = build_response.snapshot_sha256 != (previous_snapshot_sha256 or "")
        if no_report_assets_detected:
            snapshot_changed = False
        if (
            snapshot_changed
            and previous_snapshot is not None
            and build_response.new_items
            and not qualified_items
        ):
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
            snapshot_changed = False
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
            upload_response = run_with_retry(
                step_name="publisher_inventory_snapshot_upload",
                operation=lambda: deps.upload_bytes(
                    DriveUploadBytesRequest(
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
                    ),
                    ctx,
                ),
                ctx=ctx,
                logger=logger,
                module_name=logger.name,
                policy=policy,
                retry_event="publisher_inventory_snapshot_upload_retry",
                failure_event="publisher_inventory_snapshot_upload_failed",
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
            source_record = run_with_retry(
                step_name="publisher_inventory_report_source_record",
                operation=lambda item=item: deps.record_discovered_report_source(
                    ReportSourceDiscoveryRecordRequest(
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
                    ),
                    ctx,
                ),
                ctx=ctx,
                logger=logger,
                module_name=logger.name,
                policy=policy,
                retry_event="publisher_inventory_report_source_record_retry",
                failure_event="publisher_inventory_report_source_record_failed",
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
        deps.record_publisher_inventory_state(
            PublisherInventoryStateRecordRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                normalized_url=normalized_url,
                source_url=publisher_state.insights_url,
                route_kind=discovery_result.route_kind,
                route_summary=discovery_result.route_summary,
                last_final_page_url=discovery_result.final_page_url,
                snapshot_drive_file_id=snapshot_drive_file_id,
                snapshot_drive_file_name=snapshot_drive_file_name,
                snapshot_sha256=snapshot_sha256 or build_response.snapshot_sha256,
            ),
            ctx,
        )
        deps.record_publisher_inventory_test_status(
            PublisherInventoryTestStatusRecordRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                normalized_url=normalized_url,
                status=(
                    "passed:no_report_assets"
                    if no_report_assets_detected
                    else "passed"
                ),
            ),
            ctx,
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
                    "used_memory_route": response.used_memory_route,
                    "snapshot_changed": response.snapshot_changed,
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
        dependencies.record_publisher_inventory_test_status(
            PublisherInventoryTestStatusRecordRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                normalized_url=normalized_url,
                status=status,
            ),
            ctx,
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


def _is_systematic_landing_page_failure(
    *,
    screened_candidate_count: int,
    quality_response: PublisherInventoryCandidateQualityResponse,
) -> bool:
    if screened_candidate_count <= 0 or quality_response.approved_items:
        return False
    if len(quality_response.rejected_items) != screened_candidate_count:
        return False
    return all(
        decision.reason == "dead_or_unreachable_landing_page"
        for decision in quality_response.decisions
    )


def _is_no_report_assets_archive(
    *,
    previous_snapshot_available: bool,
    raw_candidate_count: int,
    screened_candidate_count: int,
    qualified_candidate_count: int,
    quality_response: PublisherInventoryCandidateQualityResponse,
) -> bool:
    if previous_snapshot_available:
        return False
    if raw_candidate_count <= 0:
        return False
    if qualified_candidate_count != 0:
        return False
    if quality_response.approved_items:
        return False
    return screened_candidate_count == 0 or bool(quality_response.rejected_items)


def _is_undercoverage_regression(
    *,
    previous_snapshot: PublisherInventorySnapshot | None,
    current_page_count: int,
    current_report_count: int,
    raw_new_report_count: int,
    qualified_candidate_count: int,
) -> bool:
    if previous_snapshot is None:
        return False
    if current_page_count <= 1 and len(previous_snapshot.pages) <= 1:
        return False
    previous_report_count = len(previous_snapshot.items)
    if previous_report_count <= 0:
        return False
    if current_report_count >= previous_report_count:
        return False
    if raw_new_report_count > 0 or qualified_candidate_count > 0:
        return False
    dropped_report_count = previous_report_count - current_report_count
    if dropped_report_count < 5:
        return False
    return current_report_count / previous_report_count <= 0.8


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
                limit=1,
                supports_all_drives=True,
                include_items_from_all_drives=True,
            ),
            ctx,
        )
        if listed.files:
            file_id = listed.files[0].file_id
            file_name = listed.files[0].name
    if not file_id:
        return None, None, None, None
    download_response = dependencies.download_pdf(
        DriveDownloadRequest(
            schema_version="1.0",
            file=DriveFile(
                schema_version="1.0",
                file_id=file_id,
                name=file_name,
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
    if not snapshot_sha256:
        snapshot_sha256 = hashlib.sha256(snapshot_payload.encode("utf-8")).hexdigest()
    snapshot = dependencies.parse_publisher_inventory_snapshot(
        snapshot_payload,
        f"drive:{file_id}",
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_previous_snapshot_loaded",
            module=logger.name,
            fields={
                "publisher_name": publisher_state.publisher_name,
                "snapshot_drive_file_id": file_id,
                "snapshot_drive_file_name": file_name or "",
                "snapshot_sha256": snapshot_sha256 or "",
                "item_count": len(snapshot.items),
            },
        )
    )
    return snapshot, file_id, file_name, snapshot_sha256


def _snapshot_file_name() -> str:
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")
    return f"{_SNAPSHOT_PREFIX}{timestamp}.json"


def _utc_now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace("+00:00", "Z")


def _source_domain_for_url(url: str) -> str:
    return str(urlsplit(str(url).strip()).hostname or "").strip().lower()
