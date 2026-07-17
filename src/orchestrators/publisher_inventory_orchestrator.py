from __future__ import annotations

"""Public coordinator for publisher-inventory orchestration.

This module remains the canonical orchestrator entrypoint. Private sibling
modules own dependency wiring, idempotent persistence, snapshot I/O, runtime
controls, and candidate post-processing.
"""

import hashlib
import inspect
import logging
import time
from dataclasses import replace

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
from src.contracts.drive import DriveFolderEnsureRequest
from src.contracts.report_store import (
    PublisherGoogleFolderUpdateRequest,
    PublisherInventoryTestStatusRecordRequest,
    PublisherInventoryStateGetRequest,
    PublisherInventoryRunQualityRecordRequest,
    PublisherInventoryStateRecordRequest,
)
from src.contracts.remediation import RemediationArtifactReference
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
from src.orchestrators._publisher_inventory_orchestrator.snapshot_records import (
    _record_qualified_report_sources,
    _upload_snapshot_if_changed,
)
from src.orchestrators.retry_orchestrator import (
    RetryPolicy,
    is_retryable_app_error,
    run_with_retry,
)
from src.orchestrators.remediation_orchestrator import (
    record_workflow_failure,
    remediation_input_checksum,
)
from src.services import llm_service
from src.utils.drive_utils import extract_drive_folder_id
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.publisher_inventory_orchestrator")


def _accepts_keyword(callable_obj, keyword: str) -> bool:
    try:
        parameters = inspect.signature(callable_obj).parameters
    except (TypeError, ValueError):
        return False
    return keyword in parameters or any(
        parameter.kind == inspect.Parameter.VAR_KEYWORD
        for parameter in parameters.values()
    )


def _run_publisher_inventory_discovery(
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
        folder_id = _ensure_missing_publisher_drive_folder(
            request=request,
            normalized_url=normalized_url,
            publisher_name=publisher_state.publisher_name,
            ctx=ctx,
            dependencies=deps,
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
        screening_openai_client = llm_service.build_client_for_settings(
            request.settings,
            scope="publisher_inventory_candidate_screening",
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
            **(
                {"openai_client": screening_openai_client}
                if _accepts_keyword(
                    deps.screen_publisher_inventory_candidates, "openai_client"
                )
                else {}
            ),
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
        (
            snapshot_drive_file_id,
            snapshot_drive_file_name,
            snapshot_sha256,
        ) = _upload_snapshot_if_changed(
            snapshot_changed=snapshot_changed,
            previous_snapshot_file_id=previous_snapshot_file_id,
            previous_snapshot_file_name=previous_snapshot_file_name,
            previous_snapshot_sha256=previous_snapshot_sha256,
            build_response=build_response,
            folder_id=folder_id,
            normalized_url=normalized_url,
            reports_db=request.reports_db,
            settings=request.settings,
            deadline_monotonic=deadline_monotonic,
            policy=policy,
            ctx=ctx,
            dependencies=deps,
        )
        _record_qualified_report_sources(
            qualified_items=qualified_items,
            page_url_by_number=page_url_by_number,
            publisher_name=publisher_state.publisher_name,
            publisher_insights_url=publisher_state.insights_url,
            normalized_url=normalized_url,
            reports_db=request.reports_db,
            discovered_at_utc=build_response.snapshot.discovered_at_utc,
            deadline_monotonic=deadline_monotonic,
            policy=policy,
            ctx=ctx,
            dependencies=deps,
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


def run_publisher_inventory_discovery(
    request: PublisherInventoryDiscoveryRequest,
    *,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies | None = None,
) -> PublisherInventoryDiscoveryResult:
    """Discover publisher inventory with an explicit terminal-failure ledger hook."""

    try:
        return _run_publisher_inventory_discovery(
            request, ctx=ctx, dependencies=dependencies
        )
    except Exception as exc:
        record_workflow_failure(
            state_db=request.state_db,
            workflow="publisher_inventory_discovery",
            stage="workflow",
            operation="run_publisher_inventory_discovery",
            error=exc,
            ctx=ctx,
            input_checksum=remediation_input_checksum(
                {
                    "insights_url": request.insights_url,
                    "reports_db": request.reports_db,
                }
            ),
            source_id=request.insights_url,
            reusable_artifacts=[
                RemediationArtifactReference(
                    schema_version="1.0",
                    name="publisher_inventory_reports_db",
                    reference=request.reports_db,
                )
            ],
        )
        raise


def _ensure_missing_publisher_drive_folder(
    *,
    request: PublisherInventoryDiscoveryRequest,
    normalized_url: str,
    publisher_name: str,
    ctx: RunContext,
    dependencies: PublisherInventoryDependencies,
) -> str:
    parent_folder_id = extract_drive_folder_id(request.settings.drive_parent_folder_id)
    clean_publisher_name = str(publisher_name or "").strip()
    if not parent_folder_id:
        _record_test_status_if_needed(
            request=PublisherInventoryTestStatusRecordRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                normalized_url=normalized_url,
                status="failed:publisher_inventory_google_folder_parent_missing",
            ),
            ctx=ctx,
            dependencies=dependencies,
        )
        raise AppError(
            code="publisher_inventory_google_folder_parent_missing",
            message="Publisher discovery cannot create a missing Drive folder without a parent folder",
            retryable=False,
            severity="error",
            context={
                "publisher_name": clean_publisher_name,
                "normalized_url": normalized_url,
            },
        )
    if not clean_publisher_name:
        raise AppError(
            code="publisher_inventory_publisher_name_missing",
            message="Publisher discovery cannot create a Drive folder without a publisher name",
            retryable=False,
            severity="error",
            context={"normalized_url": normalized_url},
        )
    policy = RetryPolicy(
        retries=request.settings.retry_retries,
        base_delay_seconds=request.settings.retry_base_delay_seconds,
        backoff_step_seconds=request.settings.retry_backoff_step_seconds,
        jitter_seconds=request.settings.retry_jitter_seconds,
    )
    ensure_response = run_with_retry(
        step_name="publisher_inventory_drive_folder_ensure",
        operation=lambda: dependencies.ensure_folder(
            DriveFolderEnsureRequest(
                schema_version="1.0",
                parent_folder_id=parent_folder_id,
                folder_name=clean_publisher_name,
                service_account_path=request.settings.google_sa_path,
                supports_all_drives=True,
                include_items_from_all_drives=True,
                drive_id=None,
                auth_mode=request.settings.drive_auth_mode,
                oauth_client_path=request.settings.google_oauth_client_path,
                oauth_token_path=request.settings.google_oauth_token_path,
            ),
            ctx,
        ),
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=policy,
        retry_event="publisher_inventory_drive_folder_ensure_retry",
        failure_event="publisher_inventory_drive_folder_ensure_failed",
    )
    folder_id = ensure_response.folder.file_id.strip()
    google_folder = f"https://drive.google.com/drive/folders/{folder_id}"
    dependencies.update_publisher_google_folder(
        PublisherGoogleFolderUpdateRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            publisher_name=clean_publisher_name,
            publisher_insights_url=normalized_url,
            google_folder=google_folder,
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="publisher_inventory_drive_folder_created",
            module=logger.name,
            fields={
                "publisher_name": clean_publisher_name,
                "normalized_url": normalized_url,
                "parent_folder_id": parent_folder_id,
                "folder_id": folder_id,
                "google_folder": google_folder,
                "created": ensure_response.created,
            },
        )
    )
    return folder_id


__all__ = [name for name in globals() if not name.startswith("__")]
