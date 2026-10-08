from __future__ import annotations

import json

from src.contracts.run_context import RunContext
from src.contracts.state import (
    MailboxCandidateRejection,
    MailboxCandidateRejectionListRequest,
    MailboxCandidateRejectionListResponse,
    MailboxCandidateRejectionRecordRequest,
    MailDeliveryRequest,
    MailDeliveryRequestByKeyGetRequest,
    MailDeliveryRequestByKeyGetResponse,
    MailDeliveryRequestGetRequest,
    MailDeliveryRequestGetResponse,
    MailDeliveryRequestListDueRequest,
    MailDeliveryRequestListDueResponse,
    MailDeliveryRequestMarkAttemptRequest,
    MailDeliveryRequestMarkAttemptResponse,
    MailDeliveryRequestUpsertRequest,
    MailDeliveryRequestUpsertResponse,
)
from src.services._state_service.common import _state_conn, logger
from src.utils.clock import utc_now_seconds_z
from src.utils.errors import AppError
from src.utils.logging import log_event


def upsert_mail_delivery_request(
    request: MailDeliveryRequestUpsertRequest,
    ctx: RunContext,
) -> MailDeliveryRequestUpsertResponse:
    now = utc_now_seconds_z()
    _validate_upsert_request(request)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mail_delivery_request_upsert_start",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "source_url": request.source_url,
                "publisher_name": request.publisher_name,
                "has_delivery_email": bool(request.delivery_email),
                "route_family": request.route_family,
            },
        )
    )
    with _state_conn(request.state_db, ctx) as conn:
        insert = conn.execute(
            """
            INSERT INTO mail_delivery_requests(
              idempotency_key, source_url, report_title, publisher_name,
              delivery_email, requested_after_utc, route_family, route_history_id,
              status, next_attempt_after_utc, created_at_utc, updated_at_utc,
              publisher_id, source_identity_id, submission_confirmed_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(idempotency_key) DO NOTHING
            """,
            (
                request.idempotency_key,
                request.source_url,
                request.report_title,
                request.publisher_name,
                request.delivery_email,
                request.requested_after_utc,
                request.route_family,
                request.route_history_id,
                request.status,
                request.requested_after_utc or now,
                now,
                now,
                request.publisher_id,
                request.source_identity_id,
                request.submission_confirmed_at_utc,
            ),
        )
        row = conn.execute(
            "SELECT * FROM mail_delivery_requests WHERE idempotency_key=?",
            (request.idempotency_key,),
        ).fetchone()
        if (
            request.status == "pending"
            and request.submission_confirmed_at_utc
            and str(row[9] or "") == "submission_started"
        ):
            if not _same_submission_identity(row, request):
                raise AppError(
                    code="mail_delivery_submission_identity_mismatch",
                    message="Confirmed mail submission does not match its durable intent",
                    retryable=False,
                )
            conn.execute(
                """
                UPDATE mail_delivery_requests
                SET report_title=?, publisher_name=?, requested_after_utc=?,
                    route_family=?, route_history_id=?, status='pending',
                    next_attempt_after_utc=?, submission_confirmed_at_utc=?,
                    updated_at_utc=?
                WHERE id=? AND status='submission_started'
                """,
                (
                    request.report_title,
                    request.publisher_name,
                    request.requested_after_utc,
                    request.route_family,
                    request.route_history_id,
                    request.requested_after_utc,
                    request.submission_confirmed_at_utc,
                    now,
                    int(row[0]),
                ),
            )
            row = conn.execute(
                "SELECT * FROM mail_delivery_requests WHERE idempotency_key=?",
                (request.idempotency_key,),
            ).fetchone()
        elif request.status == "pending" and request.submission_confirmed_at_utc:
            if (
                str(row[9] or "") == "pending"
                and str(row[6] or "") != request.submission_confirmed_at_utc
            ):
                raise AppError(
                    code="mail_delivery_submission_watermark_mismatch",
                    message="Confirmed mail submission conflicts with its persisted watermark",
                    retryable=False,
                )
    response = MailDeliveryRequestUpsertResponse(
        schema_version="1.0",
        request=_row_to_mail_delivery_request(row),
        created=insert.rowcount == 1,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mail_delivery_request_upsert_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "request_id": response.request.request_id,
                "created": response.created,
                "status": response.request.status,
            },
        )
    )
    return response


def get_mail_delivery_request(
    request: MailDeliveryRequestGetRequest,
    ctx: RunContext,
) -> MailDeliveryRequestGetResponse:
    if request.request_id <= 0:
        raise AppError(
            code="mail_delivery_request_id_invalid",
            message="Mail delivery request ID must be a positive integer",
            retryable=False,
        )
    with _state_conn(request.state_db, ctx) as conn:
        row = conn.execute(
            "SELECT * FROM mail_delivery_requests WHERE id=?",
            (request.request_id,),
        ).fetchone()
    if row is None:
        raise AppError(
            code="mail_delivery_request_not_found",
            message="Mail delivery request does not exist",
            retryable=False,
            context={"request_id": request.request_id},
        )
    return MailDeliveryRequestGetResponse(
        schema_version="1.0",
        request=_row_to_mail_delivery_request(row),
    )


def get_mail_delivery_request_by_key(
    request: MailDeliveryRequestByKeyGetRequest,
    ctx: RunContext,
) -> MailDeliveryRequestByKeyGetResponse:
    key = str(request.idempotency_key or "").strip()
    if not key:
        raise AppError(
            code="mail_delivery_idempotency_key_missing",
            message="Mail delivery request idempotency key is required",
            retryable=False,
        )
    with _state_conn(request.state_db, ctx) as conn:
        row = conn.execute(
            "SELECT * FROM mail_delivery_requests WHERE idempotency_key=?",
            (key,),
        ).fetchone()
    return MailDeliveryRequestByKeyGetResponse(
        schema_version="1.0",
        request=_row_to_mail_delivery_request(row) if row is not None else None,
    )


def list_due_mail_delivery_requests(
    request: MailDeliveryRequestListDueRequest,
    ctx: RunContext,
) -> MailDeliveryRequestListDueResponse:
    now = str(request.now_utc or "").strip()
    if not now:
        raise AppError(
            code="mail_delivery_request_now_missing",
            message="now_utc is required to list due mail delivery requests",
            retryable=False,
        )
    limit = max(1, int(request.limit or 50))
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mail_delivery_request_list_due_start",
            module=logger.name,
            fields={"state_db": request.state_db, "now_utc": now, "limit": limit},
        )
    )
    with _state_conn(request.state_db, ctx) as conn:
        rows = conn.execute(
            """
            SELECT * FROM mail_delivery_requests
            WHERE status='pending' AND next_attempt_after_utc <= ?
            ORDER BY next_attempt_after_utc ASC, id ASC
            LIMIT ?
            """,
            (now, limit),
        ).fetchall()
    response = MailDeliveryRequestListDueResponse(
        schema_version="1.0",
        requests=[_row_to_mail_delivery_request(row) for row in rows],
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mail_delivery_request_list_due_complete",
            module=logger.name,
            fields={"state_db": request.state_db, "count": len(response.requests)},
        )
    )
    return response


def mark_mail_delivery_request_attempt(
    request: MailDeliveryRequestMarkAttemptRequest,
    ctx: RunContext,
) -> MailDeliveryRequestMarkAttemptResponse:
    now = utc_now_seconds_z()
    seen_json = json.dumps(
        _dedupe_strings(request.seen_provider_message_ids),
        sort_keys=True,
        ensure_ascii=True,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mail_delivery_request_attempt_update_start",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "request_id": request.request_id,
                "status": request.status,
                "outcome": request.outcome,
                "error_code": request.error_code,
            },
        )
    )
    with _state_conn(request.state_db, ctx) as conn:
        conn.execute(
            """
            UPDATE mail_delivery_requests
            SET status=?,
                next_attempt_after_utc=?,
                attempt_count=attempt_count + 1,
                provider_cursor=?,
                seen_provider_message_ids_json=?,
                outcome=?,
                selected_message_id=?,
                downloaded_file_path=?,
                error_code=?,
                updated_at_utc=?
            WHERE id=?
            """,
            (
                request.status,
                request.next_attempt_after_utc,
                request.provider_cursor,
                seen_json,
                request.outcome,
                request.selected_message_id,
                request.downloaded_file_path,
                request.error_code,
                now,
                request.request_id,
            ),
        )
        row = conn.execute(
            "SELECT * FROM mail_delivery_requests WHERE id=?",
            (request.request_id,),
        ).fetchone()
    if row is None:
        raise AppError(
            code="mail_delivery_request_not_found",
            message="Mail delivery request does not exist",
            retryable=False,
            context={"request_id": request.request_id},
        )
    response = MailDeliveryRequestMarkAttemptResponse(
        schema_version="1.0",
        request=_row_to_mail_delivery_request(row),
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mail_delivery_request_attempt_update_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "request_id": response.request.request_id,
                "attempt_count": response.request.attempt_count,
                "status": response.request.status,
            },
        )
    )
    return response


def record_mailbox_candidate_rejection(
    request: MailboxCandidateRejectionRecordRequest,
    ctx: RunContext,
) -> None:
    now = utc_now_seconds_z()
    sender = _sanitize_sender(request.sender)
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_candidate_rejection_record_start",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "request_id": request.request_id,
                "provider_message_id": request.provider_message_id,
                "source_host": request.source_host,
                "link_host": request.link_host,
                "reason_code": request.reason_code,
            },
        )
    )
    with _state_conn(request.state_db, ctx) as conn:
        conn.execute(
            """
            INSERT INTO mailbox_candidate_rejections(
              request_id, provider_message_id, sender, source_host, link_host,
              publisher_affinity, title_token_overlap, reason_code, expires_at_utc,
              created_at_utc
            ) VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)
            ON CONFLICT(request_id, provider_message_id, link_host, reason_code)
            DO UPDATE SET
              sender=excluded.sender,
              source_host=excluded.source_host,
              publisher_affinity=excluded.publisher_affinity,
              title_token_overlap=excluded.title_token_overlap,
              expires_at_utc=excluded.expires_at_utc
            """,
            (
                int(request.request_id),
                request.provider_message_id,
                sender,
                request.source_host,
                request.link_host,
                request.publisher_affinity,
                float(request.title_token_overlap),
                request.reason_code,
                request.expires_at_utc,
                now,
            ),
        )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_candidate_rejection_record_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "request_id": request.request_id,
                "reason_code": request.reason_code,
            },
        )
    )


def list_mailbox_candidate_rejections(
    request: MailboxCandidateRejectionListRequest,
    ctx: RunContext,
) -> MailboxCandidateRejectionListResponse:
    limit = max(1, int(request.limit or 50))
    with _state_conn(request.state_db, ctx) as conn:
        rows = conn.execute(
            """
            SELECT *
            FROM mailbox_candidate_rejections
            WHERE request_id=? AND expires_at_utc >= ?
            ORDER BY created_at_utc DESC, id DESC
            LIMIT ?
            """,
            (int(request.request_id), request.now_utc, limit),
        ).fetchall()
    response = MailboxCandidateRejectionListResponse(
        schema_version="1.0",
        rejections=[_row_to_mailbox_candidate_rejection(row) for row in rows],
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_candidate_rejection_list_complete",
            module=logger.name,
            fields={
                "state_db": request.state_db,
                "request_id": request.request_id,
                "count": len(response.rejections),
            },
        )
    )
    return response


def _validate_upsert_request(request: MailDeliveryRequestUpsertRequest) -> None:
    missing = []
    if not str(request.idempotency_key or "").strip():
        missing.append("idempotency_key")
    if not str(request.source_url or "").strip():
        missing.append("source_url")
    if request.status not in {"submission_started", "pending"}:
        missing.append("status")
    if (
        request.status != "submission_started"
        and not str(request.requested_after_utc or "").strip()
    ):
        missing.append("requested_after_utc")
    if request.status == "submission_started" and (
        request.requested_after_utc or request.submission_confirmed_at_utc
    ):
        missing.append("unconfirmed_submission_watermark")
    if (
        request.submission_confirmed_at_utc
        and request.requested_after_utc != request.submission_confirmed_at_utc
    ):
        missing.append("submission_watermark_mismatch")
    if missing:
        raise AppError(
            code="mail_delivery_request_invalid",
            message="Mail delivery request is missing required fields",
            retryable=False,
            context={"missing": missing},
        )


def _same_submission_identity(row, request: MailDeliveryRequestUpsertRequest) -> bool:
    return (
        str(row[1] or "") == request.idempotency_key
        and str(row[2] or "") == request.source_url
        and str(row[3] or "") == request.report_title
        and str(row[4] or "") == request.publisher_name
        and str(row[5] or "") == request.delivery_email
        and str(row[7] or "") == request.route_family
        and str(row[8] or "") == request.route_history_id
        and str(row[20] or "") == request.publisher_id
        and str(row[21] or "") == request.source_identity_id
    )


def _row_to_mail_delivery_request(row) -> MailDeliveryRequest:
    if row is None:
        raise AppError(
            code="mail_delivery_request_not_found",
            message="Mail delivery request does not exist",
            retryable=False,
        )
    try:
        seen = json.loads(str(row[13] or "[]"))
    except json.JSONDecodeError:
        seen = []
    if not isinstance(seen, list):
        seen = []
    return MailDeliveryRequest(
        schema_version="1.0",
        request_id=int(row[0]),
        idempotency_key=str(row[1] or ""),
        source_url=str(row[2] or ""),
        report_title=str(row[3] or ""),
        publisher_name=str(row[4] or ""),
        delivery_email=str(row[5] or ""),
        requested_after_utc=str(row[6] or ""),
        route_family=str(row[7] or ""),
        route_history_id=str(row[8] or ""),
        status=str(row[9] or ""),
        next_attempt_after_utc=str(row[10] or ""),
        attempt_count=int(row[11] or 0),
        provider_cursor=str(row[12] or ""),
        seen_provider_message_ids=_dedupe_strings([str(item) for item in seen]),
        outcome=str(row[14] or ""),
        selected_message_id=str(row[15] or ""),
        downloaded_file_path=str(row[16] or ""),
        error_code=str(row[17] or ""),
        created_at_utc=str(row[18] or ""),
        updated_at_utc=str(row[19] or ""),
        publisher_id=str(row[20] or ""),
        source_identity_id=str(row[21] or ""),
        submission_confirmed_at_utc=str(row[22] or ""),
    )


def _dedupe_strings(values: list[str]) -> list[str]:
    result: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip()
        marker = token.casefold()
        if not token or marker in seen:
            continue
        seen.add(marker)
        result.append(token)
    return result


def _row_to_mailbox_candidate_rejection(row) -> MailboxCandidateRejection:
    return MailboxCandidateRejection(
        schema_version="1.0",
        rejection_id=int(row[0]),
        request_id=int(row[1]),
        provider_message_id=str(row[2] or ""),
        sender=str(row[3] or ""),
        source_host=str(row[4] or ""),
        link_host=str(row[5] or ""),
        publisher_affinity=str(row[6] or ""),
        title_token_overlap=float(row[7] or 0.0),
        reason_code=str(row[8] or ""),
        expires_at_utc=str(row[9] or ""),
        created_at_utc=str(row[10] or ""),
    )


def _sanitize_sender(value: str) -> str:
    text = " ".join(str(value or "").split())
    if "<" in text and ">" in text:
        return f"{text.split('<', 1)[0].strip()} <redacted>"
    if "@" in text:
        return "<redacted>"
    return text
