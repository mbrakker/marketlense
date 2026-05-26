from __future__ import annotations

import logging

from src.contracts.browser_download import (
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    FailedAcquisitionForensicsPack,
    PublisherDownloadRouteMemory,
    ReportDownloadRoutePlanRequest,
    ReportDownloadRoutePlanStep,
    ReportDownloadOrchestratorRequest,
    ReportDownloadOrchestratorResult,
)
from src.contracts.report_store import (
    PublisherDownloadRouteGetRequest,
    PublisherDownloadRouteResponse,
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
from src.utils.logging import log_event
from src.utils.errors import AppError
from src.utils.url_utils import normalize_url
from src.orchestrators._report_download_orchestrator.candidate_readiness import (
    assert_candidate_download_ready,
)
from src.orchestrators._report_download_orchestrator.dependencies import (
    ReportDownloadDependencies,
)
from src.orchestrators._report_download_orchestrator.drive_archive import (
    archive_successful_report_artifacts,
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
    record_route_outcome,
)
from src.orchestrators._report_download_orchestrator.promotions import (
    evaluate_private_api_playbook_auto_promotion,
    evaluate_route_playbook_promotion,
)

logger = logging.getLogger("market_lense.report_download_orchestrator")


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
    assert_candidate_download_ready(
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
    record_downloaded_source(
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
    drive_uploads = archive_successful_report_artifacts(
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


__all__ = [name for name in globals() if not name.startswith("__")]
