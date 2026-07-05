from __future__ import annotations

import base64
import io
import imaplib
import logging
import re
import zipfile
from dataclasses import replace
from datetime import datetime, timedelta, timezone
from email import policy
from email.message import EmailMessage, Message
from email.parser import BytesParser
from email.utils import parsedate_to_datetime
from pathlib import Path
from typing import Any, cast
from urllib.parse import unquote

from bs4 import BeautifulSoup
from google.auth.transport.requests import Request as GoogleAuthRequest
from google.oauth2.credentials import Credentials
from googleapiclient.discovery import build

from src.contracts.mailbox_acquisition import (
    MailboxAttachment,
    MailboxAttachmentArtifact,
    MailboxAttachmentMaterializeRequest,
    MailboxAttachmentMaterializeResponse,
    MailboxAcquisitionSettings,
    MailboxMessage,
    MailboxSearchRequest,
    MailboxSearchResult,
)
from src.contracts.run_context import RunContext
from src.utils.clock import utc_now_seconds_z
from src.utils.errors import AppError
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.mailbox_acquisition_service")

_BODY_CHAR_LIMIT = 20000
_URL_RX = re.compile(r"https?://[^\s<>\"')]+", re.IGNORECASE)
_SAFE_FILENAME_RX = re.compile(r"[^A-Za-z0-9._-]+")


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
    result: MailboxSearchResult | None = None
    last_error: AppError | None = None
    provider_order = mailbox_provider_order(settings)
    for index, selected_provider in enumerate(provider_order):
        try:
            if selected_provider == "gmail":
                result = _search_gmail_messages(request, ctx)
            elif selected_provider == "imap":
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
    for attachment in request.attachments:
        artifacts.extend(_materialize_attachment(request, attachment))
    response = MailboxAttachmentMaterializeResponse(
        schema_version="1.0",
        artifacts=artifacts,
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
            fields={"provider": result.provider, "query": _sanitize_query_for_log(result.query)},
        )
    )
    return result


def mailbox_provider_order(settings: MailboxAcquisitionSettings) -> list[str]:
    provider = str(settings.provider or "").strip().lower()
    has_imap = bool(settings.imap_host and settings.imap_user and settings.imap_password)
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
        received_at_utc=received.replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
        ),
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
) -> list[MailboxAttachmentArtifact]:
    file_name = _safe_file_name(attachment.file_name)
    lower_name = file_name.casefold()
    content_type = str(attachment.content_type or "").casefold()
    if lower_name.endswith(".pdf") or content_type == "application/pdf":
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
        return _materialize_zip_pdfs(request, attachment, file_name)
    return []


def _materialize_zip_pdfs(
    request: MailboxAttachmentMaterializeRequest,
    attachment: MailboxAttachment,
    container_file_name: str,
) -> list[MailboxAttachmentArtifact]:
    artifacts: list[MailboxAttachmentArtifact] = []
    try:
        archive = zipfile.ZipFile(io.BytesIO(attachment.payload))
    except zipfile.BadZipFile:
        return []
    with archive:
        for member in archive.infolist():
            if member.is_dir() or not member.filename.casefold().endswith(".pdf"):
                continue
            payload = archive.read(member)
            file_name = _safe_file_name(Path(member.filename).name)
            path = _artifact_path(
                settings=request.settings,
                provider_message_id=request.provider_message_id,
                file_name=file_name,
            )
            path.write_bytes(payload)
            artifacts.append(
                MailboxAttachmentArtifact(
                    schema_version="1.0",
                    file_name=path.name,
                    content_type="application/pdf",
                    size_bytes=path.stat().st_size,
                    path=str(path),
                    source_container_file_name=container_file_name,
                )
            )
    return artifacts


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
        return parsed.astimezone(timezone.utc).replace(microsecond=0).isoformat().replace(
            "+00:00", "Z"
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
    "preflight_mailbox_search",
    "search_mailbox_messages",
]
