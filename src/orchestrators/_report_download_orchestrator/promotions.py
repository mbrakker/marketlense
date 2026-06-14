from __future__ import annotations

import logging

from src.contracts.browser_download import (
    BrowserReportDownloadResult,
    BrowserRoutePrivateApiAutoPromotionDetectionRequest,
    BrowserRoutePrivateApiPromotionRequest,
    ReportDownloadOrchestratorRequest,
)
from src.contracts.report_store import (
    PublisherPrivateApiCandidateObservationRecordRequest,
    PublisherPrivateApiCandidatePromotedRequest,
)
from src.contracts.run_context import RunContext
from src.utils.clock import utc_now_seconds_z as _utc_now_iso
from src.orchestrators._report_download_orchestrator.dependencies import (
    ReportDownloadDependencies,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.report_download_orchestrator")

_ROUTE_PLAYBOOK_PROMOTION_MODES = {"disabled", "dry_run", "write"}
_ROUTE_PLAYBOOK_SUCCESS_OUTCOMES = {"downloaded", "email_requested", "captured"}
_ROUTE_PLAYBOOK_VERIFIED_STATUSES = {"verified", "recovered"}


def evaluate_route_playbook_promotion(
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


def evaluate_private_api_playbook_auto_promotion(
    *,
    request: ReportDownloadOrchestratorRequest,
    result: BrowserReportDownloadResult,
    ctx: RunContext,
    dependencies: ReportDownloadDependencies,
    route_record_reused: bool,
) -> None:
    mode = str(
        getattr(request.settings, "private_api_playbook_promotion_mode", "disabled")
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
    }
    if mode == "disabled":
        _log_private_api_promotion_event(
            ctx=ctx,
            fields={**fields, "skip_reason": "promotion_disabled"},
        )
        return
    if route_record_reused:
        _log_private_api_promotion_event(
            ctx=ctx,
            fields={**fields, "skip_reason": "route_record_idempotency_reused"},
        )
        return
    try:
        detection = dependencies.detect_private_api_promotion_candidates(
            BrowserRoutePrivateApiAutoPromotionDetectionRequest(
                schema_version="1.0",
                settings=request.settings,
                result=result,
                observed_at=_utc_now_iso(),
            ),
            ctx,
        )
    except AppError as exc:
        _log_private_api_promotion_event(
            ctx=ctx,
            fields={
                **fields,
                "skip_reason": "candidate_detection_app_error",
                "error_code": exc.code,
                "error_retryable": exc.retryable,
            },
        )
        return
    if not detection.candidates:
        _log_private_api_promotion_event(
            ctx=ctx,
            fields={
                **fields,
                "candidate_count": detection.candidate_count,
                "skip_reason": detection.skipped_reason or "no_candidates",
            },
        )
        return
    for candidate in detection.candidates:
        observed_at = _utc_now_iso()
        try:
            record = dependencies.record_publisher_private_api_candidate_observation(
                PublisherPrivateApiCandidateObservationRecordRequest(
                    schema_version="1.0",
                    db_path=request.reports_db,
                    fingerprint=candidate.fingerprint,
                    publisher_host=candidate.publisher_host,
                    source_url=candidate.source_url,
                    endpoint_pattern=candidate.endpoint_pattern,
                    method=candidate.method,
                    request_shape_summary=candidate.request_shape_summary,
                    response_pdf_url_json_pointer=(
                        candidate.response_pdf_url_json_pointer
                    ),
                    expected_status_codes=list(candidate.expected_status_codes),
                    required_response_markers=list(candidate.required_response_markers),
                    fallback_route_family=candidate.fallback_route_family,
                    route_family=candidate.route_family,
                    route_kind=candidate.route_kind,
                    evidence_labels=list(candidate.evidence_labels),
                    observed_at=observed_at,
                    min_success_count=(
                        request.settings.private_api_playbook_min_success_count
                    ),
                    min_distinct_source_urls=(
                        request.settings.private_api_playbook_min_distinct_source_urls
                    ),
                ),
                ctx,
            )
        except AppError as exc:
            _log_private_api_promotion_event(
                ctx=ctx,
                fields={
                    **fields,
                    "fingerprint": candidate.fingerprint,
                    "skip_reason": "candidate_observation_app_error",
                    "error_code": exc.code,
                    "error_retryable": exc.retryable,
                },
            )
            continue
        if not record.eligible_for_promotion:
            _log_private_api_promotion_event(
                ctx=ctx,
                fields={
                    **fields,
                    "fingerprint": candidate.fingerprint,
                    "success_count": record.success_count,
                    "distinct_source_url_count": record.distinct_source_url_count,
                    "already_promoted": record.already_promoted,
                    "skip_reason": "threshold_not_met_or_already_promoted",
                },
            )
            continue
        try:
            response = dependencies.promote_private_api_evidence_to_browser_playbook(
                request=BrowserRoutePrivateApiPromotionRequest(
                    schema_version="1.0",
                    playbook_dir=request.settings.route_playbook_dir,
                    source_url=candidate.source_url,
                    route_family=candidate.route_family,
                    route_kind=candidate.route_kind,
                    endpoint_pattern=candidate.endpoint_pattern,
                    method=candidate.method,
                    request_shape_summary=candidate.request_shape_summary,
                    response_pdf_url_json_pointer=(
                        candidate.response_pdf_url_json_pointer
                    ),
                    validated_success_count=record.success_count,
                    fallback_route_family=candidate.fallback_route_family,
                    expected_status_codes=list(candidate.expected_status_codes),
                    required_response_markers=list(candidate.required_response_markers),
                    evidence_labels=list(candidate.evidence_labels),
                    observed_at=observed_at,
                    write_file=mode == "write",
                ),
                ctx=ctx,
            )
        except AppError as exc:
            _log_private_api_promotion_event(
                ctx=ctx,
                fields={
                    **fields,
                    "fingerprint": candidate.fingerprint,
                    "success_count": record.success_count,
                    "distinct_source_url_count": record.distinct_source_url_count,
                    "skip_reason": "promotion_app_error",
                    "error_code": exc.code,
                    "error_retryable": exc.retryable,
                },
            )
            continue
        if mode == "write":
            try:
                dependencies.mark_publisher_private_api_candidate_promoted(
                    PublisherPrivateApiCandidatePromotedRequest(
                        schema_version="1.0",
                        db_path=request.reports_db,
                        fingerprint=candidate.fingerprint,
                        playbook_id=response.playbook_id,
                        promoted_at=observed_at,
                    ),
                    ctx,
                )
            except AppError as exc:
                _log_private_api_promotion_event(
                    ctx=ctx,
                    fields={
                        **fields,
                        "fingerprint": candidate.fingerprint,
                        "playbook_id": response.playbook_id,
                        "skip_reason": "promotion_mark_app_error",
                        "error_code": exc.code,
                        "error_retryable": exc.retryable,
                    },
                )
                continue
        _log_private_api_promotion_event(
            ctx=ctx,
            fields={
                **fields,
                "fingerprint": candidate.fingerprint,
                "success_count": record.success_count,
                "distinct_source_url_count": record.distinct_source_url_count,
                "playbook_id": response.playbook_id,
                "playbook_path": response.path,
                "playbook_version": response.version,
                "promotion_status": response.status,
                "review_diff_line_count": len(response.review_diff.splitlines()),
            },
        )


def _log_private_api_promotion_event(
    *, ctx: RunContext, fields: dict[str, object]
) -> None:
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="report_download_private_api_promotion_evaluated",
            module=logger.name,
            fields=fields,
        )
    )
