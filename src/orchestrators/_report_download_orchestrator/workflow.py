from __future__ import annotations

import logging
import time
from dataclasses import replace
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserDownloadCaptchaHandoffPolicy,
    BrowserDownloadRouteSuppressionPolicy,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    FailedAcquisitionForensicsPack,
    PublisherDownloadRouteMemory,
    ReportDownloadOrchestratorRequest,
    ReportDownloadOrchestratorResult,
    ReportDownloadRoutePlanRequest,
    ReportDownloadRoutePlanStep,
)
from src.contracts.mailbox_acquisition import MailboxSearchRequest
from src.contracts.report_store import (
    AcquisitionRouteSuppressionRequest,
    PublisherDownloadRouteGetRequest,
    PublisherDownloadRouteResponse,
)
from src.contracts.run_budget import (
    BudgetRequest,
    BudgetSideEffectFinalizeRequest,
    RunBudgetUsage,
)
from src.contracts.run_context import RunContext
from src.contracts.state import (
    MailDeliveryRequestUpsertRequest,
    WorkflowControlObservationWriteRequest,
)
from src.contracts.workflow_control import WorkflowControlObservation
from src.orchestrators._report_download_orchestrator.budget import (
    build_report_download_budget,
    build_report_download_telemetry_budget,
    read_report_download_budget_usage,
)
from src.orchestrators._report_download_orchestrator.candidate_readiness import (
    assert_candidate_download_ready,
)
from src.orchestrators._report_download_orchestrator.dependencies import (
    ReportDownloadDependencies,
)
from src.orchestrators._report_download_orchestrator.drive_archive import (
    archive_successful_report_artifacts,
    preflight_required_drive_archive,
)
from src.orchestrators._report_download_orchestrator.failure_forensics import (
    failure_error_class,
    persist_failed_attempt_forensics_pack,
    terminal_evidence_from_error_context,
    with_failure_forensics_context,
)
from src.orchestrators._report_download_orchestrator.persistence import (
    record_downloaded_source,
    record_identity_update,
    record_required_select_learning,
    record_route_outcome,
)
from src.orchestrators._report_download_orchestrator.promotions import (
    evaluate_private_api_playbook_auto_promotion,
    evaluate_route_playbook_promotion,
)
from src.orchestrators._report_download_orchestrator.resource_telemetry import (
    record_acquisition_resource_summary,
    route_suppression_policy_hash,
)
from src.orchestrators._report_download_orchestrator.route_planner import (
    plan_report_download_routes,
)
from src.orchestrators.remediation_orchestrator import record_workflow_failure
from src.orchestrators.retry_orchestrator import (
    RetryPolicy,
    is_retryable_app_error,
    run_with_retry,
)
from src.services.llm_usage_ledger_service import (
    evaluate_budget_request,
    finalize_budget_side_effect,
)
from src.utils.clock import utc_now_seconds_z
from src.utils.errors import AppError
from src.utils.logging import log_event
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.report_download_orchestrator")


def run_report_download(
    request: ReportDownloadOrchestratorRequest,
    *,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies | None = None,
) -> ReportDownloadOrchestratorResult:
    deps = dependencies or ReportDownloadDependencies.default()
    run_started_at_utc = utc_now_seconds_z()
    run_started_monotonic = time.monotonic()
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
    assert_candidate_download_ready(
        request=request, normalized_url=normalized_url, ctx=ctx
    )
    preflighted_drive_folder_id = preflight_required_drive_archive(
        request=request,
        normalized_url=normalized_url,
        ctx=ctx,
        dependencies=deps,
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

    now_seconds = int(time.time())
    route_memory = _remembered_route_memory(
        remembered_route,
        ttl_seconds=request.settings.route_memory_ttl_seconds,
        now_seconds=now_seconds,
    )
    if remembered_route is not None and route_memory is None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_route_memory_expired",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "updated_at": remembered_route.updated_at,
                    "ttl_seconds": request.settings.route_memory_ttl_seconds,
                    "exact_route_found": remembered_route.exact_route_found,
                    "decision": "fresh_discovery",
                },
            )
        )
    route_suppression_policy = request.settings.route_suppression_policy
    fresh_hard_blocker_reason = _fresh_remembered_hard_blocker_suppression_reason(
        remembered_route,
        ttl_seconds=request.settings.route_memory_ttl_seconds,
        policy=route_suppression_policy,
        captcha_handoff_policy=request.settings.captcha_handoff_policy,
        revalidate_route_policy=request.revalidate_route_policy,
        now_seconds=now_seconds,
    )
    if fresh_hard_blocker_reason is not None:
        route_family = str(remembered_route.route_family or "browser_unknown")
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_fresh_hard_blocker_suppressed",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "route_family": route_family,
                    "reason": fresh_hard_blocker_reason,
                    "avoided_browser_launches": 1,
                    "avoided_browser_model_calls": 1,
                },
            )
        )
        record_acquisition_resource_summary(
            request=request,
            ctx=ctx,
            dependencies=deps,
            started_at_utc=run_started_at_utc,
            started_monotonic=run_started_monotonic,
            route_family=route_family,
            terminal_outcome="suppressed",
            terminal_reason=fresh_hard_blocker_reason,
            avoided_operations=("browser_launch", "browser_model_call"),
        )
        raise AppError(
            code="report_download_route_suppressed",
            message=(
                "Browser route was suppressed by fresh exact "
                "terminal-blocker evidence"
            ),
            retryable=False,
            context={
                "route_family": route_family,
                "reason": fresh_hard_blocker_reason,
            },
        )
    plan = plan_report_download_routes(
        ReportDownloadRoutePlanRequest(
            schema_version="1.0",
            normalized_url=normalized_url,
            delivery_email=_resolve_deferred_delivery_email(request),
            remembered_route=route_memory,
            candidate_trace=request.candidate_trace,
            publisher_discovery_route_kind=request.publisher_discovery_route_kind,
            publisher_recommended_discovery_route_kind=request.publisher_recommended_discovery_route_kind,
        ),
        ctx,
    )
    suppression_failure_classes = tuple(
        blocker_class
        for blocker_class in route_suppression_policy.terminal_failure_classes
        if not (
            request.settings.captcha_handoff_policy.enabled
            and str(blocker_class).strip().casefold() == "blocked_captcha"
        )
    )
    suppression_hash = route_suppression_policy_hash(request)
    executable_steps: list[ReportDownloadRoutePlanStep] = []
    suppressed_steps: list[tuple[ReportDownloadRoutePlanStep, str]] = []
    for planned_step in plan.steps:
        if not planned_step.route_family.startswith("browser_"):
            executable_steps.append(planned_step)
            continue
        if not suppression_failure_classes:
            executable_steps.append(planned_step)
            continue
        suppression = deps.evaluate_acquisition_route_suppression(
            AcquisitionRouteSuppressionRequest(
                schema_version="1.0",
                db_path=request.reports_db,
                normalized_url=normalized_url,
                publisher_id=str(request.publisher_name or "").strip(),
                route_family=planned_step.route_family,
                policy_version=route_suppression_policy.schema_version,
                source_policy_compatibility_hash=suppression_hash,
                enabled=route_suppression_policy.enabled,
                minimum_sample_size=route_suppression_policy.minimum_sample_size,
                terminal_failure_threshold=(
                    route_suppression_policy.terminal_failure_threshold
                ),
                terminal_failure_classes=(
                    suppression_failure_classes
                ),
                ttl_seconds=route_suppression_policy.ttl_seconds,
                revalidation_override=request.revalidate_route_policy,
            ),
            ctx,
        )
        if suppression.suppressed:
            suppressed_steps.append((planned_step, suppression.reason))
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="report_download_route_suppressed",
                    module=logger.name,
                    fields={
                        "normalized_url": normalized_url,
                        "route_family": planned_step.route_family,
                        "decision_id": suppression.decision_id,
                        "reason": suppression.reason,
                        "sample_size": suppression.sample_size,
                        "terminal_failure_count": (suppression.terminal_failure_count),
                        "terminal_failure_rate": suppression.terminal_failure_rate,
                        "expires_at_utc": suppression.expires_at_utc,
                        "avoided_browser_launches": 1,
                        "avoided_browser_model_calls": 1,
                    },
                )
            )
        else:
            executable_steps.append(planned_step)
    if not executable_steps:
        suppressed_step, suppression_reason = suppressed_steps[0]
        record_acquisition_resource_summary(
            request=request,
            ctx=ctx,
            dependencies=deps,
            started_at_utc=run_started_at_utc,
            started_monotonic=run_started_monotonic,
            route_family=suppressed_step.route_family,
            terminal_outcome="suppressed",
            terminal_reason=suppression_reason,
            avoided_operations=("browser_launch", "browser_model_call"),
        )
        raise AppError(
            code="report_download_route_suppressed",
            message="All planned browser routes were suppressed by terminal-route evidence",
            retryable=False,
            context={
                "route_family": suppressed_step.route_family,
                "reason": suppression_reason,
            },
        )
    result: BrowserReportDownloadResult | None = None
    last_retryable_error: AppError | None = None
    last_planned_step: ReportDownloadRoutePlanStep | None = None
    for planned_step in executable_steps:
        last_planned_step = planned_step
        if planned_step.route_family == "browser_email_form":
            if _should_avoid_mailbox_preflight_for_remembered_blocker(
                remembered_route,
                ttl_seconds=request.settings.route_memory_ttl_seconds,
                revalidate_route_policy=request.revalidate_route_policy,
                now_seconds=int(time.time()),
            ):
                logger.info(
                    log_event(
                        ctx,
                        role="orchestrator",
                        event="report_download_mailbox_preflight_avoided",
                        module=logger.name,
                        fields={
                            "normalized_url": normalized_url,
                            "reason": "fresh_remembered_hard_blocker",
                            "avoided_mailbox_polls": 1,
                            "revalidate_route_policy": False,
                        },
                    )
                )
            else:
                preflight_mailbox_before_email_form(
                    request=request,
                    normalized_url=normalized_url,
                    ctx=ctx,
                    dependencies=deps,
                    route_families=[planned_step.route_family],
                )
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
                        "error_class": failure_error_class(exc),
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
                record_acquisition_resource_summary(
                    request=request,
                    ctx=ctx,
                    dependencies=deps,
                    started_at_utc=run_started_at_utc,
                    started_monotonic=run_started_monotonic,
                    route_family=planned_step.route_family,
                    terminal_outcome="failed",
                    terminal_reason=str(
                        (exc.context or {}).get("blocked_reason") or exc.code
                    ),
                )
                record_workflow_failure(
                    state_db=request.settings.state_db,
                    workflow="report_download",
                    stage=planned_step.step_name,
                    operation="download_report",
                    error=exc,
                    ctx=ctx,
                    input_checksum=normalized_url,
                    source_id=normalized_url,
                    publisher_id=request.publisher_name,
                )
                raise
            last_retryable_error = exc
            if not planned_step.fallback_on_retryable_error:
                record_acquisition_resource_summary(
                    request=request,
                    ctx=ctx,
                    dependencies=deps,
                    started_at_utc=run_started_at_utc,
                    started_monotonic=run_started_monotonic,
                    route_family=planned_step.route_family,
                    terminal_outcome="failed",
                    terminal_reason=str(
                        (exc.context or {}).get("blocked_reason") or exc.code
                    ),
                )
                record_workflow_failure(
                    state_db=request.settings.state_db,
                    workflow="report_download",
                    stage=planned_step.step_name,
                    operation="download_report",
                    error=exc,
                    ctx=ctx,
                    input_checksum=normalized_url,
                    source_id=normalized_url,
                    publisher_id=request.publisher_name,
                )
                raise
    if result is None:
        if last_retryable_error is not None:
            record_acquisition_resource_summary(
                request=request,
                ctx=ctx,
                dependencies=deps,
                started_at_utc=run_started_at_utc,
                started_monotonic=run_started_monotonic,
                route_family=(
                    last_planned_step.route_family if last_planned_step else "unknown"
                ),
                terminal_outcome="failed",
                terminal_reason=str(
                    (last_retryable_error.context or {}).get("blocked_reason")
                    or last_retryable_error.code
                ),
            )
            record_workflow_failure(
                state_db=request.settings.state_db,
                workflow="report_download",
                stage="route_plan",
                operation="download_report",
                error=last_retryable_error,
                ctx=ctx,
                input_checksum=normalized_url,
                source_id=normalized_url,
                publisher_id=request.publisher_name,
            )
            raise last_retryable_error
        error = AppError(
            code="report_download_plan_exhausted",
            message="The report download route plan completed without a result",
            retryable=True,
            context={"normalized_url": normalized_url},
        )
        record_acquisition_resource_summary(
            request=request,
            ctx=ctx,
            dependencies=deps,
            started_at_utc=run_started_at_utc,
            started_monotonic=run_started_monotonic,
            route_family=(
                last_planned_step.route_family if last_planned_step else "unknown"
            ),
            terminal_outcome="failed",
            terminal_reason=error.code,
        )
        record_workflow_failure(
            state_db=request.settings.state_db,
            workflow="report_download",
            stage="route_plan",
            operation="download_report",
            error=error,
            ctx=ctx,
            input_checksum=normalized_url,
            source_id=normalized_url,
            publisher_id=request.publisher_name,
        )
        raise error

    route_record_reused = record_route_outcome(
        request=request,
        result=result,
        ctx=ctx,
        dependencies=deps,
    )
    evaluate_route_playbook_promotion(
        request=request,
        result=result,
        ctx=ctx,
        dependencies=deps,
        route_record_reused=route_record_reused,
    )
    evaluate_private_api_playbook_auto_promotion(
        request=request,
        result=result,
        ctx=ctx,
        dependencies=deps,
        route_record_reused=route_record_reused,
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
    source_identity_id, verified_artifact_hash = record_downloaded_source(
        request=request,
        result=result,
        policy=policy,
        ctx=ctx,
        dependencies=deps,
    )
    identity_update = record_identity_update(
        request=request,
        result=result,
        ctx=ctx,
        dependencies=deps,
    )
    record_required_select_learning(
        request=request,
        result=result,
        ctx=ctx,
        dependencies=deps,
    )
    record_deferred_mail_delivery_request(
        request=request,
        result=result,
        ctx=ctx,
        dependencies=deps,
        run_started_at_utc=run_started_at_utc,
    )
    drive_uploads = archive_successful_report_artifacts(
        request=request,
        result=result,
        normalized_url=normalized_url,
        policy=policy,
        ctx=ctx,
        dependencies=deps,
        preflighted_folder_id=preflighted_drive_folder_id,
    )
    record_acquisition_resource_summary(
        request=request,
        ctx=ctx,
        dependencies=deps,
        started_at_utc=run_started_at_utc,
        started_monotonic=run_started_monotonic,
        route_family=result.route_family,
        terminal_outcome=(
            "failed" if result.blocked_reason == "blocked_no_progress" else "success"
        ),
        terminal_reason=(
            result.blocked_reason
            if result.blocked_reason == "blocked_no_progress"
            else "verified"
            if result.route_status == "verified"
            else result.route_status
        ),
        result=result,
        source_identity_id=source_identity_id,
        verified_artifact_hash=verified_artifact_hash,
        drive_uploads=drive_uploads,
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
    run_budget = build_report_download_budget(request, ctx)
    service_request = BrowserReportDownloadRequest(
        schema_version="1.0",
        url=request.url,
        settings=request.settings,
        delivery_email=_resolve_deferred_delivery_email(request),
        route_hint=planned_step.route_hint,
        route_step_hints=list(planned_step.route_step_hints),
        route_kind_hint=planned_step.route_kind_hint,
        candidate_trace=request.candidate_trace,
        publisher_discovery_route_kind=request.publisher_discovery_route_kind,
        publisher_recommended_discovery_route_kind=request.publisher_recommended_discovery_route_kind,
        attempt_url=planned_step.attempt_url,
        route_family_hint=planned_step.route_family,
        source_page_url_hint=planned_step.source_page_url_hint,
        report_title=request.report_title,
        publisher_name=request.publisher_name,
    )
    attempt_number = 0

    def _attempt_operation() -> BrowserReportDownloadResult:
        nonlocal attempt_number
        attempt_number += 1
        attempt_request = replace(
            service_request,
            run_budget=run_budget,
            run_budget_usage=read_report_download_budget_usage(run_budget, ctx),
        )
        pdf_decision = None
        if run_budget is not None:
            pdf_decision = evaluate_budget_request(
                BudgetRequest(
                    schema_version="1.0",
                    budget=run_budget,
                    run_id=ctx.run_id,
                    workflow_id="report_download",
                    publisher_id=request.publisher_name,
                    report_id=request.report_title or service_request.url,
                    resource_type="pdf_process",
                    operation="acquire_report_pdf",
                    estimated_pdfs=1,
                    idempotency_key=(
                        f"pdf-acquire:{ctx.run_id}:{planned_step.step_name}:{attempt_number}"
                    ),
                    reserve_in_flight=True,
                ),
                ctx,
            )
            if pdf_decision.decision in {"defer", "pause", "stop"}:
                raise AppError(
                    code=f"report_download_pdf_budget_{pdf_decision.decision}",
                    message="Report PDF acquisition was blocked by the canonical budget authority",
                    retryable=False,
                    context={
                        "reason_code": pdf_decision.reason_code,
                        "affected_limit": pdf_decision.affected_limit,
                        "retry_decision": (
                            "defer" if pdf_decision.decision == "defer" else "abort"
                        ),
                        "next_action": pdf_decision.next_action,
                    },
                )
        try:
            result = dependencies.download_report_with_browser_use(attempt_request, ctx)
            if (
                run_budget is not None
                and pdf_decision is not None
                and pdf_decision.reservation_key
            ):
                finalize_budget_side_effect(
                    BudgetSideEffectFinalizeRequest(
                        schema_version="1.0",
                        usage_db_path=run_budget.usage_db_path,
                        reservation_key=pdf_decision.reservation_key,
                        actual_usage=RunBudgetUsage(
                            schema_version="1.0",
                            pdfs=1 if result.downloaded_file_path else 0,
                        ),
                    ),
                    ctx,
                )
            return result
        except AppError as exc:
            if (
                run_budget is not None
                and pdf_decision is not None
                and pdf_decision.reservation_key
            ):
                finalize_budget_side_effect(
                    BudgetSideEffectFinalizeRequest(
                        schema_version="1.0",
                        usage_db_path=run_budget.usage_db_path,
                        reservation_key=pdf_decision.reservation_key,
                        actual_usage=RunBudgetUsage(schema_version="1.0"),
                        outcome="failed",
                        error_code=exc.code,
                    ),
                    ctx,
                )
            pack: FailedAcquisitionForensicsPack | None = None
            try:
                pack = persist_failed_attempt_forensics_pack(
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
            raise with_failure_forensics_context(
                exc,
                pack=pack,
                terminal_evidence=terminal_evidence_from_error_context(
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
            "error_class": failure_error_class(exc),
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


def _is_download_attempt_retryable(
    *,
    exc: Exception,
    planned_step: ReportDownloadRoutePlanStep,
) -> bool:
    if not is_retryable_app_error(exc):
        return False
    if not isinstance(exc, AppError):
        return False
    if (
        planned_step.route_family.startswith("browser_")
        and exc.code == "browser_download_route_summary_too_weak"
    ):
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
    *,
    ttl_seconds: int,
    now_seconds: int,
) -> PublisherDownloadRouteMemory | None:
    if remembered_route is None:
        return None
    updated_at = max(0, int(remembered_route.updated_at))
    if (
        updated_at <= 0
        or updated_at > now_seconds
        or now_seconds - updated_at > max(1, ttl_seconds)
    ):
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
        updated_at=updated_at,
        route_policy=list(remembered_route.route_policy),
        publisher_route_policy=list(remembered_route.publisher_route_policy),
    )


def _should_avoid_mailbox_preflight_for_remembered_blocker(
    remembered_route: PublisherDownloadRouteResponse | None,
    *,
    ttl_seconds: int,
    revalidate_route_policy: bool,
    now_seconds: int,
) -> bool:
    """Skip mailbox work only for fresh exact hard-blocker evidence."""
    if revalidate_route_policy or remembered_route is None:
        return False
    if (
        _remembered_route_memory(
            remembered_route,
            ttl_seconds=ttl_seconds,
            now_seconds=now_seconds,
        )
        is None
    ):
        return False
    evidence_labels = {
        str(label or "").strip().casefold()
        for label in remembered_route.terminal_evidence.evidence_labels
    }
    blocker_reason = str(remembered_route.blocked_reason or "").strip().casefold()
    return bool(
        remembered_route.exact_route_found
        and str(remembered_route.route_family or "").strip() == "browser_email_form"
        and (
            blocker_reason in {"blocked_captcha", "blocked_email_domain"}
            or {"blocked_captcha", "blocked_email_domain"} & evidence_labels
        )
    )


def _fresh_remembered_hard_blocker_suppression_reason(
    remembered_route: PublisherDownloadRouteResponse | None,
    *,
    ttl_seconds: int,
    policy: BrowserDownloadRouteSuppressionPolicy,
    captcha_handoff_policy: BrowserDownloadCaptchaHandoffPolicy,
    revalidate_route_policy: bool,
    now_seconds: int,
) -> str | None:
    """Return a policy-compatible fresh exact blocker that may skip browser work."""
    if revalidate_route_policy or not policy.enabled or remembered_route is None:
        return None
    if (
        _remembered_route_memory(
            remembered_route,
            ttl_seconds=ttl_seconds,
            now_seconds=now_seconds,
        )
        is None
    ):
        return None
    blocker_reason = str(remembered_route.blocked_reason or "").strip().casefold()
    evidence_labels = {
        str(label or "").strip().casefold()
        for label in remembered_route.terminal_evidence.evidence_labels
    }
    if (
        not remembered_route.exact_route_found
        or not str(remembered_route.route_family or "").startswith("browser_")
        or str(remembered_route.route_status or "").strip().casefold() != "verified"
        or str(remembered_route.terminal_evidence.artifact_validation_status or "")
        .strip()
        .casefold()
        != "blocked"
        or blocker_reason not in evidence_labels
        or blocker_reason
        not in {
            str(item or "").strip().casefold()
            for item in policy.terminal_failure_classes
        }
    ):
        return None
    if blocker_reason == "blocked_captcha" and captcha_handoff_policy.enabled:
        return None
    return f"fresh_remembered_{blocker_reason}"


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


def record_deferred_mail_delivery_request(
    *,
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
    run_started_at_utc: str,
) -> None:
    if result.outcome != "email_requested":
        return
    if request.mailbox_settings is None:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_mail_delivery_request_skipped",
                module=logger.name,
                fields={
                    "normalized_url": result.normalized_url,
                    "reason": "mailbox_settings_missing",
                    "outcome": result.outcome,
                },
            )
        )
        return
    delivery_email = _resolve_deferred_delivery_email(request)
    if not delivery_email:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_mail_delivery_request_skipped",
                module=logger.name,
                fields={
                    "normalized_url": result.normalized_url,
                    "reason": "delivery_email_missing",
                    "outcome": result.outcome,
                },
            )
        )
        return
    publisher_name = _mail_delivery_publisher_name(request)
    report_title = _mail_delivery_report_title(request, result)
    idempotency_key = "|".join(
        [
            "mail_delivery",
            normalize_url(result.normalized_url or request.url),
            delivery_email.casefold(),
        ]
    )
    upsert_response = dependencies.upsert_mail_delivery_request(
        MailDeliveryRequestUpsertRequest(
            schema_version="1.0",
            state_db=request.state_db,
            idempotency_key=idempotency_key,
            source_url=request.url,
            report_title=report_title,
            publisher_name=publisher_name,
            delivery_email=delivery_email,
            requested_after_utc=run_started_at_utc,
            route_family=result.route_family,
            route_history_id="",
        ),
        ctx,
    )
    dependencies.write_workflow_control_observation(
        WorkflowControlObservationWriteRequest(
            schema_version="1.0",
            state_db=request.state_db,
            observation=WorkflowControlObservation(
                schema_version="1.0",
                observed_at_utc=utc_now_seconds_z(),
                run_id=ctx.run_id,
                workflow="mail_acquisition",
                step_name="defer_mail_delivery_request",
                route=result.route_family,
                publisher=publisher_name,
                report_key=result.normalized_url or request.url,
                outcome="deferred",
                error_code="",
                error_retryable=False,
                error_severity="",
                latency_ms=0,
                cost_usd=0.0,
                retry_count=0,
                resource_pressure={
                    "mail_delivery_request_id": upsert_response.request.request_id,
                    "created": 1 if upsert_response.created else 0,
                },
            ),
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_mail_delivery_request_deferred",
            module=logger.name,
            fields={
                "normalized_url": result.normalized_url,
                "request_id": upsert_response.request.request_id,
                "created": upsert_response.created,
                "publisher_name": publisher_name,
                "route_family": result.route_family,
            },
        )
    )


def _mail_delivery_report_title(
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult,
) -> str:
    if request.report_title.strip():
        return request.report_title.strip()
    if request.candidate_trace is not None and request.candidate_trace.title.strip():
        return request.candidate_trace.title.strip()
    return result.route_summary.strip() or result.normalized_url or request.url


def _mail_delivery_publisher_name(request: ReportDownloadOrchestratorRequest) -> str:
    if request.publisher_name.strip():
        return request.publisher_name.strip()
    scope = _publisher_scope_url_for_request(request) or request.url
    host = str(urlsplit(scope).hostname or "").strip().lower()
    return host or "unknown_publisher"


def _resolve_deferred_delivery_email(
    request: ReportDownloadOrchestratorRequest,
) -> str:
    explicit = str(request.delivery_email or "").strip()
    if explicit:
        return explicit
    mailbox_email = _resolve_mailbox_delivery_email(request)
    if mailbox_email:
        return mailbox_email
    for email in request.settings.identity_profile.delivery_emails:
        token = str(email or "").strip()
        if token:
            return token
    for field in request.settings.identity_profile.fields:
        if field.key == "work_email" and str(field.value or "").strip():
            return str(field.value or "").strip()
    return ""


def _resolve_mailbox_delivery_email(request: ReportDownloadOrchestratorRequest) -> str:
    settings = request.mailbox_settings
    if settings is None:
        return ""
    provider = str(settings.provider or "").strip().casefold()
    candidates: list[str] = []
    if provider == "imap":
        candidates.append(str(settings.imap_user or "").strip())
    if provider == "gmail":
        candidates.append(str(settings.gmail_user_id or "").strip())
    candidates.extend(
        [
            str(settings.imap_user or "").strip(),
            str(settings.gmail_user_id or "").strip(),
        ]
    )
    for candidate in candidates:
        if _looks_like_email_address(candidate):
            return candidate
    return ""


def _looks_like_email_address(value: str) -> bool:
    token = str(value or "").strip()
    if "@" not in token:
        return False
    local, domain = token.rsplit("@", 1)
    return bool(local.strip() and "." in domain and domain.rsplit(".", 1)[-1].strip())


def preflight_mailbox_before_email_form(
    *,
    request: ReportDownloadOrchestratorRequest,
    normalized_url: str,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
    route_families: list[str],
) -> None:
    if request.mailbox_settings is None:
        return
    normalized_families = {str(family or "").strip() for family in route_families}
    if normalized_families and normalized_families <= {"direct_pdf_probe"}:
        return
    delivery_email = _resolve_deferred_delivery_email(request)
    if not delivery_email:
        return
    dependencies.preflight_mailbox_search(
        MailboxSearchRequest(
            schema_version="1.0",
            settings=request.mailbox_settings,
            delivery_email=delivery_email,
            source_url=request.url,
            report_title=_mail_delivery_report_title_for_request(
                request, normalized_url
            ),
            publisher_name=_mail_delivery_publisher_name(request),
            query_terms=[],
            run_budget=build_report_download_telemetry_budget(request, ctx),
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_mailbox_preflight_complete",
            module=logger.name,
            fields={
                "normalized_url": normalized_url,
                "provider": request.mailbox_settings.provider,
                "has_delivery_email": bool(delivery_email),
            },
        )
    )


def _mail_delivery_report_title_for_request(
    request: ReportDownloadOrchestratorRequest,
    normalized_url: str,
) -> str:
    if request.report_title.strip():
        return request.report_title.strip()
    if request.candidate_trace is not None and request.candidate_trace.title.strip():
        return request.candidate_trace.title.strip()
    return normalized_url or request.url


__all__ = [name for name in globals() if not name.startswith("__")]
