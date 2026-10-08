from __future__ import annotations

import base64
import imaplib
import io
import logging
import os
import re
import struct
import zipfile
import zlib
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, Callable, cast
from urllib.parse import unquote
from uuid import uuid4

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from google_auth_httplib2 import AuthorizedHttp
from googleapiclient.discovery import build
import httplib2

from src.contracts.mailbox_acquisition import (
    MailboxAcquisitionSettings,
    MailboxAttachment,
    MailboxAttachmentArtifact,
    MailboxAttachmentFailure,
    MailboxAttachmentMaterializeRequest,
    MailboxAttachmentMaterializeResponse,
    MailboxAccessPreflightResponse,
    MailboxMessage,
    MailboxSearchRequest,
    MailboxSearchResult,
)
from src.contracts.run_budget import (
    BudgetDecision,
    BudgetRequest,
    BudgetSideEffectFinalizeRequest,
    RunBudget,
    RunBudgetUsage,
)
from src.contracts.run_context import RunContext
from src.services.llm_usage_ledger_service import (
    evaluate_budget_request,
    finalize_budget_side_effect,
)
from src.utils.clock import utc_now_seconds_z
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.mailbox_acquisition_service")

_BODY_CHAR_LIMIT = 20000
_MIB = 1024 * 1024
_MAX_ZIP_ATTACHMENT_BYTES = 25 * _MIB
_MAX_ZIP_MEMBERS = 500
_MAX_ZIP_MEMBER_BYTES = 16 * _MIB
_MAX_ZIP_TOTAL_BYTES = 32 * _MIB
_MAX_ZIP_PDF_COUNT = 100
_MAX_ZIP_COMPRESSION_RATIO = 100.0
_ZIP_READ_CHUNK_BYTES = 64 * 1024
_SUPPORTED_ZIP_COMPRESSION_TYPES = {zipfile.ZIP_STORED, zipfile.ZIP_DEFLATED}
_MAILBOX_ATTACHMENT_CANDIDATE_ERROR_CODES = {
    "mailbox_attachment_too_large",
    "mailbox_zip_attachment_too_large",
    "mailbox_zip_compression_ratio_exceeded",
    "mailbox_zip_duplicate_pdf_name",
    "mailbox_zip_encrypted_entry",
    "mailbox_zip_invalid",
    "mailbox_zip_invalid_member_size",
    "mailbox_zip_member_count_exceeded",
    "mailbox_zip_member_read_failed",
    "mailbox_zip_member_size_exceeded",
    "mailbox_zip_pdf_count_exceeded",
    "mailbox_zip_total_size_exceeded",
    "mailbox_zip_unsupported_compression",
}
_URL_RX = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_SAFE_FILENAME_RX = re.compile(r"[^A-Za-z0-9._-]+")


def _mailbox_budget(request: MailboxSearchRequest, ctx: RunContext) -> RunBudget:
    if request.run_budget is not None:
        return request.run_budget
    return RunBudget(
        schema_version="1.0", run_id=ctx.run_id, publisher_name=request.publisher_name
    )


def _reserve_mailbox_read(
    request: MailboxSearchRequest, ctx: RunContext
) -> tuple[RunBudget, BudgetDecision]:
    budget = _mailbox_budget(request, ctx)
    decision = evaluate_budget_request(
        BudgetRequest(
            schema_version="1.0",
            budget=budget,
            run_id=ctx.run_id,
            workflow_id="mail_report_acquisition",
            publisher_id=request.publisher_name or budget.publisher_name,
            report_id=request.report_title,
            resource_type="mailbox_read",
            operation="search_mailbox_messages",
            estimated_mailbox_reads=1,
            idempotency_key=(
                f"mailbox-read:{ctx.run_id}:{ctx.task_id}:{ctx.span_id}:"
                f"{request.source_url}:{max(0, request.poll_number)}"
            ),
            reserve_in_flight=True,
        ),
        ctx,
    )
    if decision.decision in {"defer", "pause", "stop"}:
        raise AppError(
            code=f"mailbox_search_budget_{decision.decision}",
            message="Mailbox search was blocked by the canonical budget authority",
            retryable=False,
            context={
                "reason_code": decision.reason_code,
                "affected_limit": decision.affected_limit,
                "retry_decision": "defer" if decision.decision == "defer" else "abort",
                "next_action": decision.next_action,
            },
        )
    return budget, decision


def _finalize_mailbox_read(
    *,
    budget: RunBudget,
    decision: BudgetDecision,
    ctx: RunContext,
    outcome: str,
    actual_reads: int,
    error_code: str = "",
) -> None:
    if not decision.reservation_key:
        return
    finalize_budget_side_effect(
        BudgetSideEffectFinalizeRequest(
            schema_version="1.0",
            usage_db_path=budget.usage_db_path,
            reservation_key=decision.reservation_key,
            actual_usage=RunBudgetUsage(
                schema_version="1.0", mailbox_reads=max(0, actual_reads)
            ),
            outcome=outcome,
            error_code=error_code,
        ),
        ctx,
    )


def search_mailbox_messages(
    request: MailboxSearchRequest,
    ctx: RunContext,
) -> MailboxSearchResult:
    settings = request.settings
    provider = str(settings.provider or "").strip().lower()
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_search_start",
            module=logger.name,
            fields={
                "provider": provider,
                "has_delivery_email": bool(request.delivery_email),
                "source_url": request.source_url,
                "search_window_minutes": settings.search_window_minutes,
                "max_results": settings.max_results,
            },
        )
    )
    budget, budget_decision = _reserve_mailbox_read(request, ctx)
    result: MailboxSearchResult | None = None
    last_error: AppError | None = None
    provider_attempts = 0
    provider_order = mailbox_provider_order(settings)
    try:
        for index, selected_provider in enumerate(provider_order):
            try:
                if selected_provider == "gmail":
                    provider_attempts += 1
                    result = _search_gmail_messages(request, ctx)
                elif selected_provider == "imap":
                    provider_attempts += 1
                    result = _search_imap_messages(request, ctx)
                else:
                    raise AppError(
                        code="mailbox_provider_unsupported",
                        message="Mailbox provider must be `gmail`, `imap`, or `auto`",
                        retryable=False,
                        context={"provider": selected_provider},
                    )
                break
            except AppError as exc:
                last_error = exc
                remaining = provider_order[index + 1 :]
                if not exc.retryable or not remaining:
                    raise
                logger.info(
                    log_event(
                        ctx,
                        role="service",
                        event="mailbox_provider_fallback",
                        module=logger.name,
                        fields={
                            "failed_provider": selected_provider,
                            "error_code": exc.code,
                            "fallback_provider": remaining[0],
                        },
                    )
                )
                continue
        if result is None:
            if last_error is not None:
                raise last_error
            raise AppError(
                code="mailbox_provider_unsupported",
                message="No supported mailbox provider is configured",
                retryable=False,
                context={"provider": provider},
            )
    except AppError as exc:
        _finalize_mailbox_read(
            budget=budget,
            decision=budget_decision,
            ctx=ctx,
            outcome="failed",
            actual_reads=provider_attempts,
            error_code=exc.code,
        )
        raise
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_search_complete",
            module=logger.name,
            fields={
                "provider": result.provider,
                "message_count": len(result.messages),
                "query": _sanitize_query_for_log(result.query),
            },
        )
    )
    _finalize_mailbox_read(
        budget=budget,
        decision=budget_decision,
        ctx=ctx,
        outcome="completed",
        actual_reads=provider_attempts,
    )
    return result


def materialize_mailbox_attachments(
    request: MailboxAttachmentMaterializeRequest,
    ctx: RunContext,
) -> MailboxAttachmentMaterializeResponse:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_attachment_materialization_start",
            module=logger.name,
            fields={
                "provider_message_id": request.provider_message_id,
                "attachment_count": len(request.attachments),
            },
        )
    )
    artifacts: list[MailboxAttachmentArtifact] = []
    failures: list[MailboxAttachmentFailure] = []
    for attachment_index, attachment in enumerate(request.attachments):
        try:
            artifacts.extend(_materialize_attachment(request, attachment, ctx))
        except AppError as exc:
            if exc.code not in _MAILBOX_ATTACHMENT_CANDIDATE_ERROR_CODES:
                raise
            failures.append(
                MailboxAttachmentFailure(
                    schema_version="1.0",
                    attachment_index=attachment_index,
                    error_code=exc.code,
                )
            )
            logger.warning(
                log_event(
                    ctx,
                    role="service",
                    event="mailbox_attachment_candidate_rejected",
                    module=logger.name,
                    fields={
                        "provider_message_id": request.provider_message_id,
                        "attachment_index": attachment_index,
                        "error_code": exc.code,
                    },
                )
            )
    response = MailboxAttachmentMaterializeResponse(
        schema_version="2.0",
        artifacts=artifacts,
        failures=failures,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_attachment_materialization_complete",
            module=logger.name,
            fields={
                "provider_message_id": request.provider_message_id,
                "artifact_count": len(response.artifacts),
                "failure_count": len(response.failures),
            },
        )
    )
    return response


def preflight_mailbox_search(
    request: MailboxSearchRequest,
    ctx: RunContext,
) -> MailboxSearchResult:
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_search_preflight_start",
            module=logger.name,
            fields={
                "provider": request.settings.provider,
                "has_delivery_email": bool(request.delivery_email),
            },
        )
    )
    result = search_mailbox_messages(
        replace(
            request,
            settings=replace(request.settings, max_results=1),
            seen_provider_message_ids=[],
        ),
        ctx,
    )
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_search_preflight_complete",
            module=logger.name,
            fields={
                "provider": result.provider,
                "query": _sanitize_query_for_log(result.query),
            },
        )
    )
    return result


def preflight_mailbox_access(
    settings: MailboxAcquisitionSettings,
    ctx: RunContext,
) -> MailboxAccessPreflightResponse:
    """Verify mailbox login with one metadata-only request and no message reads."""

    errors: list[AppError] = []
    provider_calls = 0
    for provider in mailbox_provider_order(settings):
        try:
            if provider == "gmail":
                provider_calls += _preflight_gmail_access(settings)
            elif provider == "imap":
                provider_calls += 1
                _preflight_imap_access(settings)
            else:
                continue
            response = MailboxAccessPreflightResponse(
                schema_version="1.0",
                provider=provider,
                accessible=True,
                provider_calls=provider_calls,
            )
            logger.info(
                log_event(
                    ctx,
                    role="service",
                    event="mailbox_access_preflight_complete",
                    module=logger.name,
                    fields={
                        "provider": response.provider,
                        "accessible": response.accessible,
                        "provider_calls": response.provider_calls,
                    },
                )
            )
            return response
        except AppError as exc:
            if provider == "gmail":
                provider_calls += max(0, int(exc.context.get("provider_calls", 0) or 0))
            errors.append(exc)

    if errors:
        error = errors[-1]
        raise AppError(
            code=error.code,
            message="Mailbox access preflight failed for configured providers",
            cause=error,
            retryable=error.retryable,
            context={"provider_calls": provider_calls},
        ) from error
    raise AppError(
        code="mailbox_provider_unconfigured",
        message="No supported mailbox provider is configured",
        retryable=False,
    )


def _preflight_gmail_access(settings: MailboxAcquisitionSettings) -> int:
    token_path = Path(settings.gmail_oauth_token_path).expanduser().resolve()
    if not settings.gmail_oauth_token_path or not token_path.is_file():
        raise AppError(
            code="mailbox_gmail_token_missing",
            message="Gmail OAuth token is not configured",
            retryable=False,
        )
    provider_calls = 0
    try:
        credentials = Credentials.from_authorized_user_file(str(token_path))
        if credentials.expired and credentials.refresh_token:
            provider_calls += 1
            credentials.refresh(_bounded_google_auth_request(timeout_seconds=5.0))
        service = build(
            "gmail",
            "v1",
            http=AuthorizedHttp(
                credentials,
                http=httplib2.Http(timeout=5.0),
                max_refresh_attempts=0,
            ),
            cache_discovery=False,
        )
        profile_request = service.users().getProfile(
            userId=settings.gmail_user_id or "me"
        )
        provider_calls += 1
        profile_request.execute(num_retries=0)
        return provider_calls
    except Exception as exc:
        status_code = getattr(exc, "status_code", None)
        invalid_auth = status_code in {400, 401, 403}
        raise AppError(
            code=(
                "mailbox_gmail_credentials_invalid"
                if invalid_auth
                else "mailbox_gmail_unavailable"
            ),
            message="Gmail mailbox access preflight failed",
            cause=exc,
            retryable=not invalid_auth,
            context={"provider_calls": provider_calls},
        ) from exc


def _bounded_google_auth_request(*, timeout_seconds: float) -> Callable[..., Any]:
    request = GoogleAuthRequest()

    def bounded_request(url: str, **kwargs: Any) -> Any:
        kwargs["timeout"] = timeout_seconds
        return request(url, **kwargs)

    return bounded_request


def _preflight_imap_access(settings: MailboxAcquisitionSettings) -> None:
    _validate_imap_settings(settings)
    try:
        with imaplib.IMAP4_SSL(
            settings.imap_host,
            settings.imap_port,
            timeout=5.0,
        ) as connection:
            connection.login(settings.imap_user, settings.imap_password)
            status, _ = connection.select(
                settings.imap_mailbox or "INBOX", readonly=True
            )
            if status != "OK":
                raise imaplib.IMAP4.error("mailbox selection failed")
    except AppError:
        raise
    except imaplib.IMAP4.error as exc:
        invalid_auth = any(
            marker in str(exc).casefold()
            for marker in ("authenticationfailed", "login failed", "auth failed")
        )
        raise AppError(
            code=(
                "mailbox_imap_credentials_invalid"
                if invalid_auth
                else "mailbox_imap_unavailable"
            ),
            message="IMAP mailbox access preflight failed",
            cause=exc,
            retryable=not invalid_auth,
        ) from exc
    except Exception as exc:
        raise AppError(
            code="mailbox_imap_unavailable",
            message="IMAP mailbox access preflight failed",
            cause=exc,
            retryable=True,
        ) from exc


def mailbox_provider_order(settings: MailboxAcquisitionSettings) -> list[str]:
    provider = str(settings.provider or "").strip().lower()
    has_imap = bool(
        settings.imap_host and settings.imap_user and settings.imap_password
    )
    if provider == "gmail":
        return ["gmail", "imap"] if has_imap else ["gmail"]
    if provider == "imap":
        return ["imap"]
    if provider == "auto":
        order = []
        if has_imap:
            order.append("imap")
        if settings.gmail_oauth_token_path:
            order.append("gmail")
        return order or ["gmail"]
    return [provider]


def _search_gmail_messages(
    request: MailboxSearchRequest,
    ctx: RunContext,
) -> MailboxSearchResult:
    settings = request.settings
    if not settings.gmail_oauth_token_path:
        raise AppError(
            code="mailbox_gmail_token_missing",
            message="Gmail OAuth token path is required for Gmail mailbox acquisition",
            retryable=False,
        )
    token_path = Path(settings.gmail_oauth_token_path).expanduser().resolve()
    if not token_path.exists():
        raise AppError(
            code="mailbox_gmail_token_missing",
            message="Gmail OAuth token file does not exist",
            retryable=False,
            context={"token_path": str(token_path)},
        )
    creds = Credentials.from_authorized_user_file(str(token_path))
    if creds.expired and creds.refresh_token:
        creds.refresh(GoogleAuthRequest())
    service = build("gmail", "v1", credentials=creds, cache_discovery=False)
    query = _gmail_query(request)
    try:
        response = (
            service.users()
            .messages()
            .list(
                userId=settings.gmail_user_id or "me",
                q=query,
                maxResults=max(settings.max_results, 1),
            )
            .execute()
        )
        messages_payload = response.get("messages", []) or []
        messages: list[MailboxMessage] = []
        seen_ids = _seen_message_ids(request)
        for item in messages_payload[: settings.max_results]:
            message_id = str(item.get("id") or "").strip()
            if not message_id or message_id.casefold() in seen_ids:
                continue
            full = (
                service.users()
                .messages()
                .get(
                    userId=settings.gmail_user_id or "me",
                    id=message_id,
                    format="full",
                )
                .execute()
            )
            messages.append(_adapt_gmail_message(full, service, settings, ctx))
    except Exception as exc:  # pragma: no cover - provider envelope
        raise AppError(
            code="mailbox_gmail_search_failed",
            message="Gmail mailbox search failed",
            retryable=True,
            cause=exc,
            context={"query": _sanitize_query_for_log(query)},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_gmail_messages_adapted",
            module=logger.name,
            fields={"message_count": len(messages)},
        )
    )
    return MailboxSearchResult(
        schema_version="1.0",
        provider="gmail",
        searched_at_utc=utc_now_seconds_z(),
        query=query,
        messages=messages,
    )


def _search_imap_messages(
    request: MailboxSearchRequest,
    ctx: RunContext,
) -> MailboxSearchResult:
    settings = request.settings
    _validate_imap_settings(settings)
    since = datetime.now(timezone.utc) - timedelta(
        minutes=max(settings.search_window_minutes, 1)
    )
    since_token = since.strftime("%d-%b-%Y")
    query = f'SINCE "{since_token}"'
    try:
        with imaplib.IMAP4_SSL(settings.imap_host, settings.imap_port) as conn:
            conn.login(settings.imap_user, settings.imap_password)
            conn.select(settings.imap_mailbox or "INBOX")
            status, data = conn.search(None, "SINCE", since_token)
            if status != "OK":
                raise RuntimeError(f"IMAP search returned {status}")
            ids = (data[0] or b"").split()
            seen_ids = _seen_message_ids(request)
            selected_ids = [
                item
                for item in list(reversed(ids))
                if item.decode("ascii", "ignore").casefold() not in seen_ids
            ][: settings.max_results]
            messages: list[MailboxMessage] = []
            for raw_id in selected_ids:
                fetch_status, fetch_data = conn.fetch(raw_id, "(RFC822)")
                if fetch_status != "OK":
                    continue
                for payload in fetch_data:
                    if not isinstance(payload, tuple) or len(payload) < 2:
                        continue
                    parsed = BytesParser(policy=policy.default).parsebytes(payload[1])
                    messages.append(
                        _adapt_email_message(
                            parsed,
                            provider_message_id=raw_id.decode("ascii", "ignore"),
                            settings=settings,
                            ctx=ctx,
                        )
                    )
                    break
    except AppError:
        raise
    except Exception as exc:  # pragma: no cover - provider envelope
        raise AppError(
            code="mailbox_imap_search_failed",
            message="IMAP mailbox search failed",
            retryable=True,
            cause=exc,
            context={"host": settings.imap_host, "mailbox": settings.imap_mailbox},
        ) from exc
    logger.info(
        log_event(
            ctx,
            role="service",
            event="mailbox_imap_messages_adapted",
            module=logger.name,
            fields={"message_count": len(messages)},
        )
    )
    return MailboxSearchResult(
        schema_version="1.0",
        provider="imap",
        searched_at_utc=utc_now_seconds_z(),
        query=query,
        messages=messages,
    )


def _validate_imap_settings(settings: MailboxAcquisitionSettings) -> None:
    missing = []
    if not settings.imap_host:
        missing.append("IMAP_HOST")
    if not settings.imap_user:
        missing.append("IMAP_USER")
    if not settings.imap_password:
        missing.append("IMAP_PASS")
    if missing:
        raise AppError(
            code="mailbox_imap_credentials_missing",
            message="IMAP mailbox credentials are incomplete",
            retryable=False,
            context={"missing": missing},
        )


def _gmail_query(request: MailboxSearchRequest) -> str:
    settings = request.settings
    days = max(1, int((max(settings.search_window_minutes, 1) + 1439) / 1440))
    terms = [
        _quote_gmail_term(term)
        for term in request.query_terms
        if str(term or "").strip()
    ]
    query_parts = [f"newer_than:{days}d"]
    if request.delivery_email:
        query_parts.append(f"to:{request.delivery_email}")
    if terms:
        query_parts.append(" OR ".join(terms[:5]))
    return " ".join(query_parts)


def _quote_gmail_term(term: str) -> str:
    token = str(term or "").strip().replace('"', "")
    if " " in token:
        return f'"{token}"'
    return token


def _sanitize_query_for_log(query: str) -> str:
    return re.sub(
        r"[A-Z0-9._%+-]+@[A-Z0-9.-]+\.[A-Z]{2,}",
        "<redacted-email>",
        str(query or ""),
        flags=re.IGNORECASE,
    )


def _adapt_gmail_message(
    payload: dict[str, Any],
    service,
    settings: MailboxAcquisitionSettings,
    ctx: RunContext,
) -> MailboxMessage:
    message_id = str(payload.get("id") or "").strip()
    headers = _gmail_headers(payload.get("payload", {}).get("headers", []) or [])
    text_body, html_body, attachments = _gmail_message_parts(
        payload.get("payload", {}) or {},
        service=service,
        message_id=message_id,
        user_id=settings.gmail_user_id or "me",
    )
    internal_ms = int(str(payload.get("internalDate") or "0") or "0")
    received = datetime.fromtimestamp(internal_ms / 1000, tz=timezone.utc)
    links = _extract_links(text_body=text_body, html_body=html_body)
    artifacts = materialize_mailbox_attachments(
        MailboxAttachmentMaterializeRequest(
            schema_version="1.0",
            settings=settings,
            provider_message_id=message_id,
            attachments=attachments,
        ),
        ctx,
    ).artifacts
    return MailboxMessage(
        schema_version="1.0",
        provider_message_id=message_id,
        subject=headers.get("subject", ""),
        sender=headers.get("from", ""),
        received_at_utc=received.replace(microsecond=0)
        .isoformat()
        .replace("+00:00", "Z"),
        text_body=text_body[:_BODY_CHAR_LIMIT],
        html_body=html_body[:_BODY_CHAR_LIMIT],
        links=links,
        attachment_file_names=[attachment.file_name for attachment in attachments],
        attachment_artifacts=artifacts,
    )


def _gmail_headers(headers: list[dict[str, Any]]) -> dict[str, str]:
    result: dict[str, str] = {}
    for header in headers:
        name = str(header.get("name") or "").strip().lower()
        value = str(header.get("value") or "").strip()
        if name in {"subject", "from", "date"}:
            result[name] = value
    return result


def _gmail_message_parts(
    payload: dict[str, Any],
    *,
    service,
    message_id: str,
    user_id: str,
) -> tuple[str, str, list[MailboxAttachment]]:
    text_chunks: list[str] = []
    html_chunks: list[str] = []
    attachments: list[MailboxAttachment] = []
    stack = [payload]
    while stack:
        part = stack.pop()
        stack.extend(part.get("parts", []) or [])
        filename = str(part.get("filename") or "").strip()
        mime_type = str(part.get("mimeType") or "").lower()
        body_payload = part.get("body") or {}
        data = (body_payload.get("data") or "").strip()
        attachment_id = str(body_payload.get("attachmentId") or "").strip()
        if filename and attachment_id:
            raw_payload = (
                service.users()
                .messages()
                .attachments()
                .get(userId=user_id, messageId=message_id, id=attachment_id)
                .execute()
            )
            attachments.append(
                MailboxAttachment(
                    schema_version="1.0",
                    file_name=filename,
                    content_type=mime_type,
                    payload=_decode_gmail_body_bytes(
                        str(raw_payload.get("data") or "")
                    ),
                )
            )
            continue
        if filename and data:
            attachments.append(
                MailboxAttachment(
                    schema_version="1.0",
                    file_name=filename,
                    content_type=mime_type,
                    payload=_decode_gmail_body_bytes(data),
                )
            )
            continue
        if not data:
            continue
        decoded = _decode_gmail_body(data)
        if mime_type == "text/plain":
            text_chunks.append(decoded)
        elif mime_type == "text/html":
            html_chunks.append(decoded)
    return (
        "\n".join(text_chunks)[:_BODY_CHAR_LIMIT],
        "\n".join(html_chunks)[:_BODY_CHAR_LIMIT],
        attachments,
    )


def _decode_gmail_body(data: str) -> str:
    padded = data + ("=" * (-len(data) % 4))
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii")).decode(
            "utf-8", errors="replace"
        )
    except Exception:
        return ""


def _decode_gmail_body_bytes(data: str) -> bytes:
    padded = data + ("=" * (-len(data) % 4))
    try:
        return base64.urlsafe_b64decode(padded.encode("ascii"))
    except Exception:
        return b""


def _adapt_email_message(
    message: Message | EmailMessage,
    *,
    provider_message_id: str,
    settings: MailboxAcquisitionSettings,
    ctx: RunContext,
) -> MailboxMessage:
    text_chunks: list[str] = []
    html_chunks: list[str] = []
    attachments: list[MailboxAttachment] = []
    if message.is_multipart():
        parts: list[Any] = list(message.walk())
    else:
        parts = [cast(Any, message)]
    for part in parts:
        content_disposition = str(part.get_content_disposition() or "").lower()
        filename = str(part.get_filename() or "").strip()
        if filename:
            raw_payload = part.get_payload(decode=True) or b""
            payload = raw_payload if isinstance(raw_payload, bytes) else b""
            attachments.append(
                MailboxAttachment(
                    schema_version="1.0",
                    file_name=filename,
                    content_type=str(part.get_content_type() or ""),
                    payload=payload,
                )
            )
        if content_disposition == "attachment":
            continue
        content_type = str(part.get_content_type() or "").lower()
        try:
            body = part.get_content()
        except Exception:
            raw_body = part.get_payload(decode=True) or b""
            body = (
                raw_body.decode("utf-8", errors="replace")
                if isinstance(raw_body, bytes)
                else str(raw_body)
            )
        if content_type == "text/plain":
            text_chunks.append(str(body))
        elif content_type == "text/html":
            html_chunks.append(str(body))
    received_at = _message_date_to_utc(str(message.get("Date") or ""))
    text_body = "\n".join(text_chunks)[:_BODY_CHAR_LIMIT]
    html_body = "\n".join(html_chunks)[:_BODY_CHAR_LIMIT]
    artifacts = materialize_mailbox_attachments(
        MailboxAttachmentMaterializeRequest(
            schema_version="1.0",
            settings=settings,
            provider_message_id=provider_message_id,
            attachments=attachments,
        ),
        ctx,
    ).artifacts
    return MailboxMessage(
        schema_version="1.0",
        provider_message_id=provider_message_id,
        subject=str(message.get("Subject") or ""),
        sender=str(message.get("From") or ""),
        received_at_utc=received_at,
        text_body=text_body,
        html_body=html_body,
        links=_extract_links(text_body=text_body, html_body=html_body),
        attachment_file_names=_dedupe_strings(
            [attachment.file_name for attachment in attachments]
        ),
        attachment_artifacts=artifacts,
    )


def _materialize_attachment(
    request: MailboxAttachmentMaterializeRequest,
    attachment: MailboxAttachment,
    ctx: RunContext,
) -> list[MailboxAttachmentArtifact]:
    file_name = _safe_file_name(attachment.file_name)
    lower_name = file_name.casefold()
    content_type = str(attachment.content_type or "").casefold()
    if lower_name.endswith(".pdf") or content_type == "application/pdf":
        if len(attachment.payload) > _MAX_ZIP_ATTACHMENT_BYTES:
            raise AppError(
                code="mailbox_attachment_too_large",
                message="Mailbox PDF attachment exceeds the supported size",
                retryable=False,
            )
        path = _artifact_path(
            settings=request.settings,
            provider_message_id=request.provider_message_id,
            file_name=file_name if lower_name.endswith(".pdf") else f"{file_name}.pdf",
        )
        path.write_bytes(attachment.payload)
        return [
            MailboxAttachmentArtifact(
                schema_version="1.0",
                file_name=path.name,
                content_type="application/pdf",
                size_bytes=path.stat().st_size,
                path=str(path),
                source_container_file_name="",
            )
        ]
    if lower_name.endswith(".zip") or "zip" in content_type:
        return _materialize_zip_pdfs(request, attachment, file_name, ctx)
    return []


def _materialize_zip_pdfs(
    request: MailboxAttachmentMaterializeRequest,
    attachment: MailboxAttachment,
    container_file_name: str,
    ctx: RunContext,
) -> list[MailboxAttachmentArtifact]:
    if len(attachment.payload) > _MAX_ZIP_ATTACHMENT_BYTES:
        raise AppError(
            code="mailbox_zip_attachment_too_large",
            message="Mailbox ZIP attachment exceeds the supported size",
            retryable=False,
        )
    try:
        archive = zipfile.ZipFile(io.BytesIO(attachment.payload))
    except (
        EOFError,
        OSError,
        ValueError,
        zipfile.BadZipFile,
        zipfile.LargeZipFile,
        struct.error,
        zlib.error,
    ) as exc:
        raise AppError(
            code="mailbox_zip_invalid",
            message="Mailbox ZIP attachment is malformed or unsupported",
            cause=exc,
            retryable=False,
        ) from exc

    with archive:
        members = archive.infolist()
        if len(members) > _MAX_ZIP_MEMBERS:
            raise AppError(
                code="mailbox_zip_member_count_exceeded",
                message="Mailbox ZIP attachment contains too many members",
                retryable=False,
            )

        pdf_members: list[tuple[zipfile.ZipInfo, str]] = []
        output_names: set[str] = set()
        declared_total_bytes = 0
        for member in members:
            if member.flag_bits & 0x1:
                raise AppError(
                    code="mailbox_zip_encrypted_entry",
                    message="Encrypted mailbox ZIP entries are unsupported",
                    retryable=False,
                )
            if member.compress_type not in _SUPPORTED_ZIP_COMPRESSION_TYPES:
                raise AppError(
                    code="mailbox_zip_unsupported_compression",
                    message="Mailbox ZIP entry uses an unsupported compression method",
                    retryable=False,
                )
            if member.file_size < 0 or member.compress_size < 0:
                raise AppError(
                    code="mailbox_zip_invalid_member_size",
                    message="Mailbox ZIP entry has invalid size metadata",
                    retryable=False,
                )
            if member.file_size > _MAX_ZIP_MEMBER_BYTES:
                raise AppError(
                    code="mailbox_zip_member_size_exceeded",
                    message="Mailbox ZIP entry exceeds the supported size",
                    retryable=False,
                )
            declared_total_bytes += member.file_size
            if declared_total_bytes > _MAX_ZIP_TOTAL_BYTES:
                raise AppError(
                    code="mailbox_zip_total_size_exceeded",
                    message="Mailbox ZIP entries exceed the cumulative size limit",
                    retryable=False,
                )
            if member.file_size and (
                member.compress_size == 0
                or member.file_size / member.compress_size > _MAX_ZIP_COMPRESSION_RATIO
            ):
                raise AppError(
                    code="mailbox_zip_compression_ratio_exceeded",
                    message="Mailbox ZIP entry exceeds the supported compression ratio",
                    retryable=False,
                )
            if member.is_dir():
                continue
            if not member.filename.casefold().endswith(".pdf"):
                continue
            if len(pdf_members) >= _MAX_ZIP_PDF_COUNT:
                raise AppError(
                    code="mailbox_zip_pdf_count_exceeded",
                    message="Mailbox ZIP attachment contains too many PDF files",
                    retryable=False,
                )
            file_name = _safe_file_name(Path(member.filename).name)
            folded_file_name = file_name.casefold()
            if folded_file_name in output_names:
                raise AppError(
                    code="mailbox_zip_duplicate_pdf_name",
                    message="Mailbox ZIP contains colliding PDF output names",
                    retryable=False,
                )
            output_names.add(folded_file_name)
            pdf_members.append((member, file_name))

        materialized: list[tuple[str, bytes]] = []
        actual_total_bytes = 0
        try:
            for member, file_name in pdf_members:
                payload = _read_zip_member_bounded(
                    archive,
                    member,
                    total_bytes_read=actual_total_bytes,
                )
                actual_total_bytes += len(payload)
                materialized.append((file_name, payload))
        except AppError:
            raise

    artifacts: list[MailboxAttachmentArtifact] = []
    staged: list[tuple[Path, Path, str, int, bool]] = []
    committed_paths: set[Path] = set()
    try:
        for file_name, payload in materialized:
            path = _artifact_path(
                settings=request.settings,
                provider_message_id=request.provider_message_id,
                file_name=file_name,
            )
            temp_path = path.parent / f".{uuid4().hex}.tmp"
            existed_before = path.exists()
            staged.append((temp_path, path, file_name, len(payload), existed_before))
            with temp_path.open("xb") as temp_file:
                temp_file.write(payload)
        for temp_path, path, file_name, size_bytes, _ in staged:
            os.replace(temp_path, path)
            committed_paths.add(path)
            artifacts.append(
                MailboxAttachmentArtifact(
                    schema_version="1.0",
                    file_name=file_name,
                    content_type="application/pdf",
                    size_bytes=size_bytes,
                    path=str(path),
                    source_container_file_name=container_file_name,
                )
            )
    except Exception as exc:
        existed_by_path = {path: existed for _, path, _, _, existed in staged}
        for temp_path, _, _, _, _ in staged:
            try:
                temp_path.unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    log_event(
                        ctx,
                        role="service",
                        event="mailbox_zip_temp_cleanup_failed",
                        module=logger.name,
                        fields={"provider_message_id": request.provider_message_id},
                    )
                )
        for path in committed_paths:
            if existed_by_path.get(path, False):
                continue
            try:
                path.unlink(missing_ok=True)
            except OSError:
                logger.warning(
                    log_event(
                        ctx,
                        role="service",
                        event="mailbox_zip_output_cleanup_failed",
                        module=logger.name,
                        fields={"provider_message_id": request.provider_message_id},
                    )
                )
        if isinstance(exc, AppError):
            raise
        raise AppError(
            code="mailbox_zip_write_failed",
            message="Mailbox ZIP PDF artifacts could not be written atomically",
            cause=exc,
            retryable=True,
        ) from exc
    return artifacts


def _read_zip_member_bounded(
    archive: zipfile.ZipFile,
    member: zipfile.ZipInfo,
    *,
    total_bytes_read: int,
) -> bytes:
    payload = bytearray()
    try:
        with archive.open(member, "r") as member_stream:
            while chunk := member_stream.read(_ZIP_READ_CHUNK_BYTES):
                if len(payload) + len(chunk) > _MAX_ZIP_MEMBER_BYTES:
                    raise AppError(
                        code="mailbox_zip_member_size_exceeded",
                        message=(
                            "Mailbox ZIP entry exceeded the supported streamed size"
                        ),
                        retryable=False,
                    )
                if total_bytes_read + len(payload) + len(chunk) > _MAX_ZIP_TOTAL_BYTES:
                    raise AppError(
                        code="mailbox_zip_total_size_exceeded",
                        message=(
                            "Mailbox ZIP entries exceeded the cumulative streamed size"
                        ),
                        retryable=False,
                    )
                payload.extend(chunk)
    except AppError:
        raise
    except (
        EOFError,
        NotImplementedError,
        OSError,
        RuntimeError,
        ValueError,
        zipfile.BadZipFile,
        struct.error,
        zlib.error,
    ) as exc:
        raise AppError(
            code="mailbox_zip_member_read_failed",
            message="Mailbox ZIP entry could not be read safely",
            cause=exc,
            retryable=False,
        ) from exc
    if len(payload) != member.file_size:
        raise AppError(
            code="mailbox_zip_member_read_failed",
            message="Mailbox ZIP entry size did not match its metadata",
            retryable=False,
        )
    return bytes(payload)


def _artifact_path(
    *,
    settings: MailboxAcquisitionSettings,
    provider_message_id: str,
    file_name: str,
) -> Path:
    root = Path(settings.output_dir).expanduser().resolve()
    message_dir = (root / _safe_file_name(provider_message_id or "message")).resolve()
    if root != message_dir and root not in message_dir.parents:
        raise AppError(
            code="mailbox_attachment_output_dir_invalid",
            message="Mailbox attachment output path escaped the configured root",
            retryable=False,
        )
    message_dir.mkdir(parents=True, exist_ok=True)
    path = (message_dir / _safe_file_name(file_name)).resolve()
    if root != path and root not in path.parents:
        raise AppError(
            code="mailbox_attachment_output_dir_invalid",
            message="Mailbox attachment output path escaped the configured root",
            retryable=False,
        )
    return path


def _safe_file_name(value: str) -> str:
    token = _SAFE_FILENAME_RX.sub("_", str(value or "").strip()).strip("._")
    return token or "attachment"


def _message_date_to_utc(value: str) -> str:
    try:
        parsed = parsedate_to_datetime(value)
        if parsed.tzinfo is None:
            parsed = parsed.replace(tzinfo=timezone.utc)
        return (
            parsed.astimezone(timezone.utc)
            .replace(microsecond=0)
            .isoformat()
            .replace("+00:00", "Z")
        )
    except Exception:
        return utc_now_seconds_z()


def _extract_links(*, text_body: str, html_body: str) -> list[str]:
    links: list[str] = []
    for match in _URL_RX.findall(text_body or ""):
        links.append(_clean_url(match))
    if html_body:
        soup = BeautifulSoup(html_body, "html.parser")
        for anchor in soup.find_all("a", href=True):
            links.append(_clean_url(str(anchor.get("href") or "")))
        for match in _URL_RX.findall(soup.get_text(" ")):
            links.append(_clean_url(match))
    return _dedupe_strings([link for link in links if _is_absolute_http_url(link)])


def _clean_url(value: str) -> str:
    return unquote(str(value or "").strip().rstrip(".,;:)>]}'\""))


def _is_absolute_http_url(url: str) -> bool:
    return url.lower().startswith(("http://", "https://"))


def _dedupe_strings(values: list[str]) -> list[str]:
    deduped: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip()
        marker = token.lower()
        if not token or marker in seen:
            continue
        seen.add(marker)
        deduped.append(token)
    return deduped


def _seen_message_ids(request: MailboxSearchRequest) -> set[str]:
    return {
        str(item or "").strip().casefold()
        for item in request.seen_provider_message_ids
        if str(item or "").strip()
    }


__all__ = [
    "mailbox_provider_order",
    "materialize_mailbox_attachments",
    "preflight_mailbox_access",
    "preflight_mailbox_search",
    "search_mailbox_messages",
]
