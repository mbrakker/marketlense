from __future__ import annotations

import logging
import time
from dataclasses import dataclass
from datetime import datetime, timezone
from typing import Callable

from src.contracts.browser_download import (
    ReportDownloadOrchestratorRequest,
    ReportDownloadOrchestratorResult,
)
from src.contracts.mailbox_acquisition import (
    MailReportAcquisitionRequest,
    MailReportAcquisitionResult,
    MailboxMessage,
    MailboxSearchRequest,
    MailboxSearchResult,
)
from src.contracts.run_context import RunContext
from src.generators.mail_report_acquisition_generator import (
    build_mailbox_query_terms,
    select_mail_report_link_candidates,
)
from src.orchestrators.report_download_orchestrator import run_report_download
from src.services.mailbox_acquisition_service import search_mailbox_messages
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.mail_report_acquisition_orchestrator")


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

    @classmethod
    def default(cls) -> "MailReportAcquisitionDependencies":
        return cls(
            search_mailbox_messages=search_mailbox_messages,
            run_report_download=lambda req, ctx: run_report_download(req, ctx=ctx),
            sleep_fn=time.sleep,
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
            ),
            ctx,
        )
        messages = _filter_messages_after_watermark(
            messages=mailbox_result.messages,
            requested_after=request_watermark,
            ctx=ctx,
        )
        last_message_count = len(messages)
        candidates = select_mail_report_link_candidates(
            messages=messages,
            source_url=request.source_url,
            report_title=request.report_title,
            publisher_name=request.publisher_name,
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
                            "downloaded_file_path": response.downloaded_file_path
                            or "",
                        },
                    )
                )
                return response
        remaining = deadline - time.monotonic()
        if remaining <= 0:
            _raise_not_arrived(
                request=request,
                poll_count=poll_count,
                last_message_count=last_message_count,
                last_candidate_count=last_candidate_count,
            )
        sleep_seconds = min(max(settings.poll_interval_seconds, 0.0), remaining)
        if sleep_seconds <= 0:
            _raise_not_arrived(
                request=request,
                poll_count=poll_count,
                last_message_count=last_message_count,
                last_candidate_count=last_candidate_count,
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
) -> None:
    raise AppError(
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


__all__ = ["MailReportAcquisitionDependencies", "run_mail_report_acquisition"]
