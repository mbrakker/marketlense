from __future__ import annotations

"""Public coordinator for publisher-inventory orchestration.

This module remains the canonical orchestrator entrypoint. Private sibling
modules own dependency wiring, idempotent persistence, snapshot I/O, runtime
controls, and candidate post-processing.
"""

import hashlib
import logging
import time
from dataclasses import asdict, replace

from src.contracts.drive import DriveUploadBytesRequest
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
    PublisherInventoryRoutePlanRequest,
    PublisherInventoryRunQualityEvaluationRequest,
    PublisherInventoryRunQualitySummary,
    PublisherInventoryServiceResponse,
    PublisherInventorySnapshot,
)
from src.contracts.report_store import (
    PublisherInventoryTestStatusRecordRequest,
    PublisherInventoryStateGetRequest,
    PublisherInventoryRunQualityRecordRequest,
    PublisherInventoryStateRecordRequest,
    ReportSourceDiscoveryRecordRequest,
)
from src.contracts.run_context import RunContext
from src.orchestrators._publisher_inventory_orchestrator.candidate_flow import (
    _candidate_provenance_counts,
    _log_rollout_guardrails,
    _rank_qualified_items_by_resource_quality,
    _record_deferred_candidate_recovery_cache,
    _source_domain_for_url,
)
from src.orchestrators._publisher_inventory_orchestrator.dependencies import (
    PublisherInventoryDependencies,
)
from src.orchestrators._publisher_inventory_orchestrator.idempotency import (
    _RECOVERY_CACHE_IDEMPOTENCY_SCOPE,
    _REPORT_SOURCE_RECORD_IDEMPOTENCY_SCOPE,
    _RUN_QUALITY_IDEMPOTENCY_SCOPE,
    _SNAPSHOT_UPLOAD_IDEMPOTENCY_SCOPE,
    _STATE_RECORD_IDEMPOTENCY_SCOPE,
    _TEST_STATUS_IDEMPOTENCY_SCOPE,
    _idempotency_key_with_checksum,
    _lookup_idempotency_record,
    _optional_dataclass_payload,
    _payload_optional_str,
    _record_idempotency_outcome,
    _record_recovery_cache_if_needed,
    _record_run_quality_if_needed,
    _record_state_if_needed,
    _record_test_status_if_needed,
    _recovery_cache_record_checksum,
    _restore_drive_file,
    _restore_report_source_record,
    _restore_upload_bytes_response,
    _run_quality_record_checksum,
    _state_record_checksum,
    _test_status_record_checksum,
)
from src.orchestrators._publisher_inventory_orchestrator.route_planner import (
    plan_publisher_inventory_routes,
)
from src.orchestrators._publisher_inventory_orchestrator.runtime import (
    _assert_time_budget_remaining,
    _discovery_test_status_for_error_code,
    _record_discovery_test_status_on_failure,
    _remaining_time_budget_seconds,
    _run_discovery_attempt,
    _settings_with_time_budget,
    _utc_now_iso,
)
from src.orchestrators._publisher_inventory_orchestrator.snapshot_io import (
    _SNAPSHOT_LOOKBACK_LIMIT,
    _SNAPSHOT_PREFIX,
    _load_previous_snapshot,
    _snapshot_file_name,
)
from src.orchestrators.retry_orchestrator import (
    RetryPolicy,
    is_retryable_app_error,
    run_with_retry,
)
from src.utils.cache_utils import sha256_json
from src.utils.drive_utils import extract_drive_folder_id
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.publisher_inventory_orchestrator")


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
                if not should_fallback:
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


__all__ = [name for name in globals() if not name.startswith("__")]
