from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from pathlib import Path
from typing import Callable, Optional
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserDownloadIdentityFieldUpsertRequest,
    BrowserDownloadIdentityFieldUpsertResponse,
    BrowserReportDownloadRequest,
    BrowserReportDownloadResult,
    PublisherDownloadRouteMemory,
    ReportDownloadRoutePlanRequest,
    ReportDownloadRoutePlanStep,
    ReportDownloadOrchestratorRequest,
    ReportDownloadOrchestratorResult,
)
from src.contracts.files import FileHashRequest, FileHashResponse
from src.contracts.report_store import (
    PublisherDownloadRouteGetRequest,
    PublisherDownloadRouteRecordRequest,
    PublisherDownloadRouteResponse,
    ReportSourceRecordRequest,
    ReportSourceRecordResponse,
)
from src.contracts.run_context import RunContext
from src.orchestrators.retry_orchestrator import (
    RetryPolicy,
    is_retryable_app_error,
    run_with_retry,
)
from src.orchestrators._report_download_route_planner import (
    plan_report_download_routes,
)
from src.services.browser_report_download_service import (
    download_report_with_browser_use,
)
from src.services.file_service import file_md5
from src.services.report_store_service import (
    get_publisher_download_route,
    record_publisher_download_route,
    record_report_source,
)
from src.services.config_service import upsert_browser_download_identity_fields
from src.utils.logging import log_event
from src.utils.errors import AppError
from src.utils.url_utils import normalize_url

logger = logging.getLogger("market_lense.report_download_orchestrator")
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

    @classmethod
    def default(cls) -> "ReportDownloadDependencies":
        return cls(
            download_report_with_browser_use=download_report_with_browser_use,
            get_publisher_download_route=get_publisher_download_route,
            record_publisher_download_route=record_publisher_download_route,
            file_md5=file_md5,
            record_report_source=record_report_source,
            upsert_browser_download_identity_fields=upsert_browser_download_identity_fields,
            sleep_fn=time.sleep,
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
                "publisher_discovery_route_kind": request.publisher_discovery_route_kind
                or "",
                "publisher_recommended_discovery_route_kind": (
                    request.publisher_recommended_discovery_route_kind or ""
                ),
            },
        )
    )
    _assert_candidate_download_ready(request=request, normalized_url=normalized_url, ctx=ctx)
    remembered_route = deps.get_publisher_download_route(
        PublisherDownloadRouteGetRequest(
            schema_version="1.0",
            db_path=request.reports_db,
            normalized_url=normalized_url,
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
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="report_download_memory_hit",
                module=logger.name,
                fields={
                    "normalized_url": normalized_url,
                    "route_kind": remembered_route.route_kind,
                    "outcome": remembered_route.outcome,
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
            if not is_retryable_app_error(exc):
                raise
            last_retryable_error = exc
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
                        "error_code": exc.code,
                        "error_message": exc.message,
                        "fallback_on_retryable_error": planned_step.fallback_on_retryable_error,
                    },
                )
            )
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

    deps.record_publisher_download_route(
        PublisherDownloadRouteRecordRequest(
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
        ),
        ctx,
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
        source_record = run_with_retry(
            step_name="report_download_source_record",
            operation=lambda: deps.record_report_source(
                ReportSourceRecordRequest(
                    schema_version="1.0",
                    db_path=request.reports_db,
                    source_domain=_source_domain_for_url(result.source_url),
                    report_name=_report_name_for_result(result),
                    landing_page_url=result.source_url,
                    downloaded_at_utc=_utc_now_iso(),
                    md5=file_hash.md5,
                ),
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
    identity_update = deps.upsert_browser_download_identity_fields(
        BrowserDownloadIdentityFieldUpsertRequest(
            schema_version="1.0",
            path=request.settings.identity_config_path,
            encountered_form_fields=result.encountered_form_fields,
        ),
        ctx,
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
        route_kind_hint=planned_step.route_kind_hint,
        candidate_trace=request.candidate_trace,
        publisher_discovery_route_kind=request.publisher_discovery_route_kind,
        publisher_recommended_discovery_route_kind=request.publisher_recommended_discovery_route_kind,
        attempt_url=planned_step.attempt_url,
        route_family_hint=planned_step.route_family,
        source_page_url_hint=planned_step.source_page_url_hint,
    )
    return run_with_retry(
        step_name=planned_step.step_name,
        operation=lambda: dependencies.download_report_with_browser_use(
            service_request, ctx
        ),
        ctx=ctx,
        logger=logger,
        module_name=logger.name,
        policy=policy,
        retry_event="report_download_retry",
        failure_event="report_download_attempt_failed",
        sleep_fn=dependencies.sleep_fn,
    )


def _remembered_route_memory(
    remembered_route: PublisherDownloadRouteResponse | None,
) -> PublisherDownloadRouteMemory | None:
    if remembered_route is None:
        return None
    return PublisherDownloadRouteMemory(
        schema_version="1.0",
        route_kind=remembered_route.route_kind,
        route_summary=remembered_route.route_summary,
        outcome=remembered_route.outcome,
        route_family=remembered_route.route_family,
        route_status=remembered_route.route_status,
        resolved_target_url=remembered_route.resolved_target_url,
        attempts=remembered_route.attempts,
        verified_successes=remembered_route.verified_successes,
        last_n_outcomes=list(remembered_route.last_n_outcomes),
        confidence_score=remembered_route.confidence_score,
    )


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
    title = str(candidate.title or "").strip().casefold()
    url_value = str(candidate.canonical_url or normalized_url).strip().casefold()
    if any(marker in title for marker in _REPORT_TITLE_MARKERS):
        return
    if any(marker in url_value for marker in _NON_REPORT_URL_MARKERS) or any(
        marker in title for marker in _NON_REPORT_TITLE_MARKERS
    ):
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
                },
            )
        )
        raise AppError(
            code="report_download_candidate_not_ready",
            message="The candidate URL does not look like a report acquisition target",
            retryable=False,
            context={
                "normalized_url": normalized_url,
                "candidate_title": candidate.title,
                "candidate_url": candidate.canonical_url,
            },
        )


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
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat().replace(
        "+00:00", "Z"
    )
