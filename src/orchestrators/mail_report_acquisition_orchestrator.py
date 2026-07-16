from __future__ import annotations

import logging
import re
import time
from dataclasses import dataclass
from datetime import datetime, timedelta, timezone
from typing import Callable
from urllib.parse import urlsplit

from src.contracts.browser_download import (
    BrowserDownloadConfirmationEvidence,
    BrowserDownloadRouteStep,
    DownloadTerminalEvidence,
    ReportDownloadOrchestratorRequest,
    ReportDownloadOrchestratorResult,
)
from src.contracts.mailbox_acquisition import (
    MailboxMessage,
    MailboxSearchRequest,
    MailboxSearchResult,
    MailReportAcquisitionRequest,
    MailReportAcquisitionResult,
)
from src.contracts.report_store import PublisherDownloadRouteRecordRequest
from src.contracts.run_budget import RunBudget
from src.contracts.run_context import RunContext
from src.contracts.state import (
    MailboxCandidateRejection,
    MailboxCandidateRejectionListRequest,
    MailboxCandidateRejectionRecordRequest,
)
from src.generators.mail_report_acquisition_generator import (
    build_mailbox_query_terms,
    select_mail_report_link_candidates,
)
from src.orchestrators.remediation_orchestrator import record_workflow_failure
from src.orchestrators.report_download_orchestrator import run_report_download
from src.services.mailbox_acquisition_service import search_mailbox_messages
from src.services.report_store_service import (
    record_publisher_download_route as record_publisher_download_route_service,
)
from src.services.state_service import (
    list_mailbox_candidate_rejections,
    record_mailbox_candidate_rejection,
)
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.mail_report_acquisition_orchestrator")


def _mailbox_run_budget(
    request: MailReportAcquisitionRequest, ctx: RunContext
) -> RunBudget:
    settings = request.browser_download_settings
    return RunBudget(
        schema_version="1.0",
        run_id=ctx.run_id,
        publisher_name=request.publisher_name,
        usage_db_path=settings.usage_db_path,
        max_runtime_seconds=getattr(settings, "run_budget_max_runtime_seconds", None),
        max_retries=getattr(settings, "run_budget_max_retries", None),
        max_browser_launches=getattr(
            settings, "run_budget_max_browser_launches", None
        ),
        max_pdfs=getattr(settings, "run_budget_max_pdfs", None),
        max_drive_writes=getattr(settings, "run_budget_max_drive_writes", None),
        max_mailbox_reads=getattr(settings, "run_budget_max_mailbox_reads", None),
        limit_decision=settings.run_budget_limit_decision,
        policy_version=settings.run_budget_policy_version,
        reservation_ttl_seconds=settings.run_budget_reservation_ttl_seconds,
        run_limits=settings.run_budget_limits_run,
        day_limits=settings.run_budget_limits_day,
        publisher_limits=settings.run_budget_limits_publisher,
        enabled_effect_kinds=settings.run_budget_enabled_effect_kinds,
    )


@dataclass(frozen=True)
class MailReportAcquisitionDependencies:
    search_mailbox_messages: Callable[
        [MailboxSearchRequest, RunContext], MailboxSearchResult
    ]
    run_report_download: Callable[
        [ReportDownloadOrchestratorRequest, RunContext],
        ReportDownloadOrchestratorResult,
    ]
    sleep_fn: Callable[[float], None]
    record_publisher_download_route: Callable[
        [PublisherDownloadRouteRecordRequest, RunContext], object
    ] = record_publisher_download_route_service
    list_mailbox_candidate_rejections: Callable[
        [MailboxCandidateRejectionListRequest, RunContext], object
    ] = list_mailbox_candidate_rejections
    record_mailbox_candidate_rejection: Callable[
        [MailboxCandidateRejectionRecordRequest, RunContext], object
    ] = record_mailbox_candidate_rejection

    @classmethod
    def default(cls) -> "MailReportAcquisitionDependencies":
        return cls(
            search_mailbox_messages=search_mailbox_messages,
            run_report_download=lambda req, ctx: run_report_download(req, ctx=ctx),
            sleep_fn=time.sleep,
            record_publisher_download_route=record_publisher_download_route_service,
            list_mailbox_candidate_rejections=list_mailbox_candidate_rejections,
            record_mailbox_candidate_rejection=record_mailbox_candidate_rejection,
        )


def run_mail_report_acquisition(
    request: MailReportAcquisitionRequest,
    *,
    ctx: RunContext,
    dependencies: MailReportAcquisitionDependencies | None = None,
) -> MailReportAcquisitionResult:
    deps = dependencies or MailReportAcquisitionDependencies.default()
    settings = request.mailbox_settings
    query_terms = build_mailbox_query_terms(
        publisher_name=request.publisher_name,
        report_title=request.report_title,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="mail_report_acquisition_start",
            module=logger.name,
            fields={
                "source_url": request.source_url,
                "publisher_name": request.publisher_name,
                "has_delivery_email": bool(request.delivery_email),
                "provider": settings.provider,
                "poll_timeout_seconds": settings.poll_timeout_seconds,
                "poll_interval_seconds": settings.poll_interval_seconds,
            },
        )
    )
    deadline = time.monotonic() + max(settings.poll_timeout_seconds, 0.0)
    poll_count = 0
    last_message_count = 0
    last_candidate_count = 0
    request_watermark = _parse_requested_after_utc(request.requested_after_utc)
    mailbox_budget = _mailbox_run_budget(request, ctx)
    while True:
        poll_count += 1
        mailbox_result = deps.search_mailbox_messages(
            MailboxSearchRequest(
                schema_version="1.0",
                settings=settings,
                delivery_email=request.delivery_email,
                source_url=request.source_url,
                report_title=request.report_title,
                publisher_name=request.publisher_name,
                query_terms=query_terms,
                seen_provider_message_ids=request.seen_provider_message_ids,
                run_budget=mailbox_budget,
                poll_number=poll_count,
            ),
            ctx,
        )
        messages = _filter_messages_after_watermark(
            messages=mailbox_result.messages,
            requested_after=request_watermark,
            ctx=ctx,
        )
        messages = _filter_seen_messages(
            messages=messages,
            seen_provider_message_ids=request.seen_provider_message_ids,
            ctx=ctx,
        )
        last_message_count = len(messages)
        seen_message_ids = _merge_seen_message_ids(
            request.seen_provider_message_ids,
            [message.provider_message_id for message in messages],
        )
        attachment_result = _acquire_matching_attachment(
            request=request,
            messages=messages,
            poll_count=poll_count,
            seen_message_ids=seen_message_ids,
            ctx=ctx,
        )
        if attachment_result is not None:
            _promote_mailbox_delivery_route_memory(
                request=request,
                response=attachment_result,
                ctx=ctx,
                record_route=deps.record_publisher_download_route,
            )
            return attachment_result
        candidates = select_mail_report_link_candidates(
            messages=messages,
            source_url=request.source_url,
            report_title=request.report_title,
            publisher_name=request.publisher_name,
            ctx=ctx,
        )
        rejections = _active_mailbox_candidate_rejections(
            request=request,
            ctx=ctx,
            list_rejections=deps.list_mailbox_candidate_rejections,
        )
        candidates = _suppress_rejected_mailbox_candidates(
            candidates=candidates,
            rejections=rejections,
            ctx=ctx,
        )
        last_candidate_count = len(candidates)
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="mail_report_acquisition_poll_complete",
                module=logger.name,
                fields={
                    "poll_count": poll_count,
                    "message_count": last_message_count,
                    "candidate_count": last_candidate_count,
                },
            )
        )
        for candidate in candidates:
            try:
                download_result = deps.run_report_download(
                    ReportDownloadOrchestratorRequest(
                        schema_version="1.0",
                        url=candidate.url,
                        settings=request.browser_download_settings,
                        state_db=request.browser_download_settings.state_db,
                        reports_db=request.reports_db,
                        delivery_email=None,
                        report_title=request.report_title,
                        publisher_name=request.publisher_name,
                    ),
                    ctx,
                )
            except AppError as exc:
                logger.info(
                    log_event(
                        ctx,
                        role="orchestrator",
                        event="mail_report_candidate_download_failed",
                        module=logger.name,
                        fields={
                            "candidate_url": candidate.url,
                            "error_code": exc.code,
                            "retryable": exc.retryable,
                        },
                    )
                )
                if exc.retryable:
                    error = AppError(
                        code="mail_report_candidate_download_retryable_failed",
                        message="A selected mailbox report link failed with a retryable acquisition error",
                        cause=exc,
                        retryable=True,
                        severity="warning",
                        context={
                            "source_url": request.source_url,
                            "publisher_name": request.publisher_name,
                            "candidate_url": candidate.url,
                            "candidate_error_code": exc.code,
                        },
                    )
                    record_workflow_failure(
                        state_db=request.browser_download_settings.state_db,
                        workflow="mail_report_acquisition",
                        stage="candidate_download",
                        operation="download_mail_report_link",
                        error=error,
                        ctx=ctx,
                        input_checksum=request.source_url,
                        source_id=request.source_url,
                        publisher_id=request.publisher_name,
                    )
                    raise error from exc
                _record_mailbox_candidate_rejection(
                    request=request,
                    candidate=candidate,
                    error_code=exc.code,
                    ctx=ctx,
                    record_rejection=deps.record_mailbox_candidate_rejection,
                )
                continue
            if download_result.outcome in {"downloaded", "captured"}:
                response = MailReportAcquisitionResult(
                    schema_version="1.0",
                    source_url=request.source_url,
                    outcome=download_result.outcome,
                    mailbox_poll_count=poll_count,
                    selected_report_url=candidate.url,
                    selected_message_id=candidate.provider_message_id,
                    downloaded_file_path=download_result.downloaded_file_path
                    or download_result.onsite_capture_path,
                    report_download_result=download_result,
                    acquisition_result_taxonomy=_taxonomy_for_download_result(
                        download_result
                    ),
                    seen_provider_message_ids=seen_message_ids,
                )
                logger.info(
                    log_event(
                        ctx,
                        role="orchestrator",
                        event="mail_report_acquisition_complete",
                        module=logger.name,
                        fields={
                            "source_url": response.source_url,
                            "outcome": response.outcome,
                            "mailbox_poll_count": response.mailbox_poll_count,
                            "selected_report_url": response.selected_report_url or "",
                            "downloaded_file_path": response.downloaded_file_path or "",
                        },
                    )
                )
                _promote_mailbox_delivery_route_memory(
                    request=request,
                    response=response,
                    ctx=ctx,
                    record_route=deps.record_publisher_download_route,
                )
                return response
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _raise_not_arrived(
                request=request,
                poll_count=poll_count,
                last_message_count=last_message_count,
                last_candidate_count=last_candidate_count,
                ctx=ctx,
            )
        sleep_seconds = min(max(settings.poll_interval_seconds, 0.0), remaining)
        if sleep_seconds <= 0:
            _raise_not_arrived(
                request=request,
                poll_count=poll_count,
                last_message_count=last_message_count,
                last_candidate_count=last_candidate_count,
                ctx=ctx,
            )
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="mail_report_acquisition_waiting_for_delivery",
                module=logger.name,
                fields={
                    "poll_count": poll_count,
                    "sleep_seconds": sleep_seconds,
                    "remaining_seconds": remaining,
                },
            )
        )
        deps.sleep_fn(sleep_seconds)


def _filter_messages_after_watermark(
    *,
    messages: list[MailboxMessage],
    requested_after: datetime | None,
    ctx: RunContext,
) -> list[MailboxMessage]:
    if requested_after is None:
        return messages
    selected = []
    skipped_count = 0
    for message in messages:
        received_at = _parse_message_received_at(message.received_at_utc)
        if received_at is None or received_at >= requested_after:
            selected.append(message)
        else:
            skipped_count += 1
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="mail_report_acquisition_watermark_filter_applied",
            module=logger.name,
            fields={
                "requested_after_utc": requested_after.isoformat().replace(
                    "+00:00", "Z"
                ),
                "input_message_count": len(messages),
                "selected_message_count": len(selected),
                "skipped_message_count": skipped_count,
            },
        )
    )
    return selected


def _filter_seen_messages(
    *,
    messages: list[MailboxMessage],
    seen_provider_message_ids: list[str],
    ctx: RunContext,
) -> list[MailboxMessage]:
    seen = {
        str(item or "").strip().casefold()
        for item in seen_provider_message_ids
        if str(item or "").strip()
    }
    if not seen:
        return messages
    selected = [
        message
        for message in messages
        if message.provider_message_id.casefold() not in seen
    ]
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="mail_report_acquisition_seen_filter_applied",
            module=logger.name,
            fields={
                "input_message_count": len(messages),
                "selected_message_count": len(selected),
                "skipped_message_count": len(messages) - len(selected),
            },
        )
    )
    return selected


def _acquire_matching_attachment(
    *,
    request: MailReportAcquisitionRequest,
    messages: list[MailboxMessage],
    poll_count: int,
    seen_message_ids: list[str],
    ctx: RunContext,
) -> MailReportAcquisitionResult | None:
    intent_terms = [
        token
        for token in [
            request.publisher_name,
            request.report_title,
        ]
        if len(token.strip()) >= 4
    ]
    intent_markers = {
        token.casefold()
        for token in build_mailbox_query_terms(
            publisher_name=request.publisher_name,
            report_title=request.report_title,
        )
        if len(token.strip()) >= 4
    }
    for message in messages:
        if not message.attachment_artifacts:
            continue
        message_text = " ".join([message.subject, message.text_body]).casefold()
        if intent_terms and not any(
            token.casefold() in message_text for token in intent_terms
        ):
            continue
        if intent_markers and not any(
            marker in message_text for marker in intent_markers
        ):
            continue
        for artifact in message.attachment_artifacts:
            if not artifact.path or not artifact.file_name.casefold().endswith(".pdf"):
                continue
            response = MailReportAcquisitionResult(
                schema_version="1.0",
                source_url=request.source_url,
                outcome="downloaded_attachment",
                mailbox_poll_count=poll_count,
                selected_report_url=None,
                selected_message_id=message.provider_message_id,
                downloaded_file_path=artifact.path,
                report_download_result=None,
                acquisition_result_taxonomy=(
                    "mailbox_attachment_zip_pdf"
                    if artifact.source_container_file_name
                    else "mailbox_attachment_pdf"
                ),
                seen_provider_message_ids=seen_message_ids,
            )
            logger.info(
                log_event(
                    ctx,
                    role="orchestrator",
                    event="mail_report_acquisition_attachment_complete",
                    module=logger.name,
                    fields={
                        "source_url": response.source_url,
                        "outcome": response.outcome,
                        "taxonomy": response.acquisition_result_taxonomy,
                        "selected_message_id": response.selected_message_id or "",
                        "downloaded_file_path": response.downloaded_file_path or "",
                    },
                )
            )
            return response
    return None


def _merge_seen_message_ids(
    existing: list[str],
    observed: list[str],
) -> list[str]:
    merged: list[str] = []
    seen: set[str] = set()
    for value in [*existing, *observed]:
        token = str(value or "").strip()
        marker = token.casefold()
        if not token or marker in seen:
            continue
        seen.add(marker)
        merged.append(token)
    return merged


def _taxonomy_for_download_result(
    result: ReportDownloadOrchestratorResult,
) -> str:
    if result.outcome == "captured":
        return "mailbox_inline_html_report"
    if result.route_family in {"direct_pdf_probe", "http_pdf_probe"}:
        return "mailbox_body_pdf_link"
    if "cloud" in result.route_family:
        return "mailbox_cloud_link"
    return "mailbox_download_link"


def _promote_mailbox_delivery_route_memory(
    *,
    request: MailReportAcquisitionRequest,
    response: MailReportAcquisitionResult,
    ctx: RunContext,
    record_route: Callable[[PublisherDownloadRouteRecordRequest, RunContext], object],
) -> None:
    reports_db = str(request.reports_db or "").strip()
    source_url = str(request.source_url or "").strip()
    if not reports_db or not source_url:
        return
    download_result = response.report_download_result
    terminal_kind = response.acquisition_result_taxonomy or "mailbox_delivery"
    final_page_url = (
        (download_result.final_page_url if download_result else None)
        or response.selected_report_url
        or source_url
    )
    resolved_target_url = (
        (download_result.resolved_target_url if download_result else None)
        or response.selected_report_url
        or source_url
    )
    downloaded_path = (
        download_result.downloaded_file_path if download_result else None
    ) or response.downloaded_file_path
    route_steps = (
        list(download_result.route_steps)
        if download_result is not None
        else [
            BrowserDownloadRouteStep(
                schema_version="1.0",
                index=0,
                action="poll_mailbox",
                target_text=request.publisher_name or request.report_title,
                target_role="mailbox",
                target_url=source_url,
                result="completed",
            )
        ]
    )
    confirmation_evidence = (
        download_result.confirmation_evidence
        if download_result is not None
        else BrowserDownloadConfirmationEvidence(
            schema_version="1.0",
            url_changed=False,
            visible_confirmation_text="Report delivered through configured mailbox.",
            submit_button_state="submitted",
            form_disappeared=True,
            final_page_url=final_page_url,
            confirmation_score=3,
            signal_labels=["mailbox_delivery", terminal_kind],
        )
    )
    terminal_evidence = (
        download_result.terminal_evidence
        if download_result is not None
        else DownloadTerminalEvidence(
            schema_version="1.0",
            final_page_url=final_page_url,
            final_page_title="",
            terminal_text_excerpt="Report delivered through configured mailbox.",
            artifact_url=downloaded_path or final_page_url,
            artifact_kind=terminal_kind,
            artifact_validation_status="confirmed",
            artifact_validation_detail="Mailbox delivery produced a local report artifact.",
            confirmation_signal_count=2,
            traversed_page_urls=[source_url],
            evidence_labels=["mailbox_delivery", terminal_kind],
        )
    )
    record_route(
        PublisherDownloadRouteRecordRequest(
            schema_version="1.0",
            db_path=reports_db,
            normalized_url=source_url,
            source_url=source_url,
            route_kind="email_delivery",
            route_summary=(
                "Use the configured mailbox-delivery workflow before browser launch; "
                "a previous request delivered the report successfully."
            ),
            outcome="downloaded"
            if response.outcome == "downloaded_attachment"
            else response.outcome,
            route_family="mailbox_delivery",
            route_status="verified",
            resolved_target_url=resolved_target_url,
            route_steps=route_steps,
            confirmation_evidence=confirmation_evidence,
            terminal_evidence=terminal_evidence,
            browser_had_structured_result=bool(
                download_result.browser_had_structured_result
                if download_result is not None
                else True
            ),
            used_candidate_pdf_url=bool(
                download_result.used_candidate_pdf_url
                if download_result is not None
                else False
            ),
            used_candidate_source_page=bool(
                download_result.used_candidate_source_page
                if download_result is not None
                else False
            ),
            candidate_pdf_url=response.selected_report_url,
            candidate_source_page_urls=[source_url],
            candidate_discovery_provenances=["mailbox_delivery"],
            blocked_reason=None,
            blocked_reason_detail=None,
            last_downloaded_file_path=downloaded_path,
            last_final_page_url=final_page_url,
            onsite_capture_path=(
                download_result.onsite_capture_path
                if download_result is not None
                else None
            ),
            onsite_capture_format=(
                download_result.onsite_capture_format
                if download_result is not None
                else None
            ),
            onsite_page_count=(
                download_result.onsite_page_count
                if download_result is not None
                else None
            ),
            onsite_completeness_status=(
                download_result.onsite_completeness_status
                if download_result is not None
                else None
            ),
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="orchestrator",
            event="mail_report_route_memory_promoted",
            module=logger.name,
            fields={
                "source_url": source_url,
                "outcome": response.outcome,
                "taxonomy": terminal_kind,
            },
        )
    )


def _active_mailbox_candidate_rejections(
    *,
    request: MailReportAcquisitionRequest,
    ctx: RunContext,
    list_rejections: Callable[
        [MailboxCandidateRejectionListRequest, RunContext], object
    ],
) -> list[MailboxCandidateRejection]:
    if request.workflow_request_id <= 0:
        return []
    state_db = str(request.browser_download_settings.state_db or "").strip()
    if not state_db:
        return []
    response = list_rejections(
        MailboxCandidateRejectionListRequest(
            schema_version="1.0",
            state_db=state_db,
            request_id=request.workflow_request_id,
            now_utc=datetime.now(timezone.utc).isoformat().replace("+00:00", "Z"),
            limit=50,
        ),
        ctx,
    )
    return list(getattr(response, "rejections", []) or [])


def _suppress_rejected_mailbox_candidates(
    *,
    candidates: list,
    rejections: list[MailboxCandidateRejection],
    ctx: RunContext,
) -> list:
    if not candidates or not rejections:
        return candidates
    rejected_keys = {
        (
            str(item.provider_message_id or "").casefold(),
            str(item.link_host or "").casefold(),
        )
        for item in rejections
    }
    selected = [
        candidate
        for candidate in candidates
        if (
            candidate.provider_message_id.casefold(),
            _host(candidate.url).casefold(),
        )
        not in rejected_keys
    ]
    skipped_count = len(candidates) - len(selected)
    if skipped_count:
        logger.info(
            log_event(
                ctx,
                role="orchestrator",
                event="mail_report_candidate_rejections_suppressed",
                module=logger.name,
                fields={
                    "input_candidate_count": len(candidates),
                    "selected_candidate_count": len(selected),
                    "skipped_candidate_count": skipped_count,
                },
            )
        )
    return selected


def _record_mailbox_candidate_rejection(
    *,
    request: MailReportAcquisitionRequest,
    candidate,
    error_code: str,
    ctx: RunContext,
    record_rejection: Callable[
        [MailboxCandidateRejectionRecordRequest, RunContext], object
    ],
) -> None:
    if request.workflow_request_id <= 0:
        return
    state_db = str(request.browser_download_settings.state_db or "").strip()
    if not state_db:
        return
    expires_at = (
        (datetime.now(timezone.utc) + timedelta(days=7))
        .isoformat()
        .replace("+00:00", "Z")
    )
    record_rejection(
        MailboxCandidateRejectionRecordRequest(
            schema_version="1.0",
            state_db=state_db,
            request_id=request.workflow_request_id,
            provider_message_id=candidate.provider_message_id,
            sender="",
            source_host=_host(request.source_url),
            link_host=_host(candidate.url),
            publisher_affinity="download_failed",
            title_token_overlap=_title_token_overlap(
                title=request.report_title,
                value=candidate.url,
            ),
            reason_code=error_code,
            expires_at_utc=expires_at,
        ),
        ctx,
    )


def _host(value: str) -> str:
    return str(urlsplit(str(value or "").strip()).hostname or "").lower()


def _title_token_overlap(*, title: str, value: str) -> float:
    title_tokens = _tokens(title)
    if not title_tokens:
        return 0.0
    value_tokens = _tokens(value)
    return round(len(title_tokens & value_tokens) / len(title_tokens), 3)


def _tokens(value: str) -> set[str]:
    return {
        token
        for token in re.split(r"[^a-z0-9]+", str(value or "").casefold())
        if len(token) >= 4
    }


def _parse_requested_after_utc(value: str | None) -> datetime | None:
    token = str(value or "").strip()
    if not token:
        return None
    parsed = _parse_message_received_at(token)
    if parsed is None:
        raise AppError(
            code="mail_report_invalid_request_watermark",
            message="Mail report request watermark must be a valid UTC timestamp",
            retryable=False,
            severity="error",
            context={"requested_after_utc": token},
        )
    return parsed


def _parse_message_received_at(value: str) -> datetime | None:
    token = str(value or "").strip()
    if not token:
        return None
    if token.endswith("Z"):
        token = f"{token[:-1]}+00:00"
    try:
        parsed = datetime.fromisoformat(token)
    except ValueError:
        return None
    if parsed.tzinfo is None:
        parsed = parsed.replace(tzinfo=timezone.utc)
    return parsed.astimezone(timezone.utc)


def _raise_not_arrived(
    *,
    request: MailReportAcquisitionRequest,
    poll_count: int,
    last_message_count: int,
    last_candidate_count: int,
    ctx: RunContext,
) -> None:
    error = AppError(
        code="mail_report_not_arrived_yet",
        message="The requested report email has not arrived within the configured mailbox polling window",
        retryable=True,
        severity="warning",
        context={
            "source_url": request.source_url,
            "publisher_name": request.publisher_name,
            "poll_count": poll_count,
            "message_count": last_message_count,
            "candidate_count": last_candidate_count,
        },
    )
    record_workflow_failure(
        state_db=request.browser_download_settings.state_db,
        workflow="mail_report_acquisition",
        stage="mailbox_poll",
        operation="poll_mailbox_delivery",
        error=error,
        ctx=ctx,
        input_checksum=request.source_url,
        source_id=request.source_url,
        publisher_id=request.publisher_name,
    )
    raise error


__all__ = ["MailReportAcquisitionDependencies", "run_mail_report_acquisition"]
