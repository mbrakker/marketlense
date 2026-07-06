from __future__ import annotations

import logging
import re
from urllib.parse import urlsplit

from src.contracts.mailbox_acquisition import (
    MailReportLinkCandidate,
    MailboxMessage,
)
from src.contracts.run_context import RunContext
from src.utils.logging import log_event

logger = logging.getLogger("market_lense.mail_report_acquisition_generator")

_REPORT_LINK_MARKERS = {
    "asset",
    "download",
    "ebook",
    "e-book",
    "guide",
    "pdf",
    "report",
    "research",
    "study",
    "survey",
    "trend",
    "whitepaper",
}
_NEGATIVE_LINK_MARKERS = {
    "unsubscribe",
    "preference",
    "privacy",
    "terms",
    "contact",
    "calendar",
    "linkedin",
    "facebook",
    "twitter",
    "instagram",
    "newsletter",
}


def select_mail_report_link_candidates(
    *,
    messages: list[MailboxMessage],
    source_url: str,
    report_title: str,
    publisher_name: str,
    ctx: RunContext,
) -> list[MailReportLinkCandidate]:
    source_host = str(urlsplit(str(source_url or "").strip()).hostname or "").lower()
    title_tokens = _meaningful_tokens(report_title)
    publisher_tokens = _meaningful_tokens(publisher_name)
    candidates: list[MailReportLinkCandidate] = []
    seen: set[str] = set()
    for message in messages:
        message_text = " ".join(
            [message.subject, message.sender, message.text_body]
        ).lower()
        for link in message.links:
            url = str(link or "").strip()
            if not _is_absolute_http_url(url):
                continue
            normalized_key = url.lower()
            if normalized_key in seen:
                continue
            seen.add(normalized_key)
            score, reasons, has_report_evidence = _score_link(
                url=url,
                message_text=message_text,
                link_context=_link_context(message_text=message_text, url=url),
                source_host=source_host,
                title_tokens=title_tokens,
                publisher_tokens=publisher_tokens,
            )
            if score < 2.0 or not has_report_evidence:
                continue
            candidates.append(
                MailReportLinkCandidate(
                    schema_version="1.0",
                    url=url,
                    score=score,
                    reason=", ".join(reasons),
                    provider_message_id=message.provider_message_id,
                )
            )
    candidates.sort(key=lambda item: item.score, reverse=True)
    logger.info(
        log_event(
            ctx,
            role="generator",
            event="mail_report_link_candidates_selected",
            module=logger.name,
            fields={
                "message_count": len(messages),
                "candidate_count": len(candidates),
                "top_score": candidates[0].score if candidates else 0.0,
            },
        )
    )
    return candidates


def build_mailbox_query_terms(*, publisher_name: str, report_title: str) -> list[str]:
    terms: list[str] = []
    for value in (publisher_name, report_title, "report", "download", "whitepaper"):
        token = str(value or "").strip()
        if token and token.lower() not in {item.lower() for item in terms}:
            terms.append(token)
    return terms


def _score_link(
    *,
    url: str,
    message_text: str,
    link_context: str,
    source_host: str,
    title_tokens: set[str],
    publisher_tokens: set[str],
) -> tuple[float, list[str], bool]:
    parsed = urlsplit(url)
    host = str(parsed.hostname or "").lower()
    path_query = f"{parsed.path} {parsed.query}".lower()
    haystack = f"{host} {path_query}".lower()
    if any(marker in haystack for marker in _NEGATIVE_LINK_MARKERS):
        return 0.0, ["excluded_non_report_link"], False
    if "emailwebview" in haystack:
        return 0.0, ["excluded_email_webview_link"], False
    score = 0.0
    reasons: list[str] = []
    has_report_evidence = False
    matched_title_in_message = title_tokens & _meaningful_tokens(message_text)
    message_has_report_delivery_context = (
        bool(matched_title_in_message)
        and any(marker in message_text for marker in _REPORT_LINK_MARKERS)
    )
    link_is_publisher_related = _host_matches_source(
        host=host, source_host=source_host
    ) or bool(publisher_tokens & _meaningful_tokens(f"{host} {path_query}"))
    matched_title = title_tokens & _meaningful_tokens(haystack)
    matched_publisher = publisher_tokens & _meaningful_tokens(
        f"{haystack} {message_text}"
    )
    if not (link_is_publisher_related or matched_publisher):
        return 0.0, ["excluded_cross_publisher_link"], False
    if parsed.path.lower().endswith(".pdf"):
        score += 3.0
        reasons.append("pdf_url")
        has_report_evidence = True
    if any(marker in haystack for marker in _REPORT_LINK_MARKERS):
        score += 2.0
        reasons.append("report_marker")
        has_report_evidence = True
    if matched_title:
        score += min(3.0, float(len(matched_title)))
        reasons.append("title_token_match")
        has_report_evidence = True
    if matched_publisher:
        score += min(2.0, float(len(matched_publisher)))
        reasons.append("publisher_token_match")
    if message_has_report_delivery_context and link_is_publisher_related:
        score += 2.0
        reasons.append("message_report_delivery_context")
        has_report_evidence = True
    if link_is_publisher_related and _link_context_has_report_cta(
        link_context=link_context,
        title_tokens=title_tokens,
    ):
        score += 3.0
        reasons.append("link_report_cta_context")
        has_report_evidence = True
    if _host_matches_source(host=host, source_host=source_host):
        score += 1.0
        reasons.append("source_host_match")
    return score, reasons or ["weak_match"], has_report_evidence


def _link_context(
    *,
    message_text: str,
    url: str,
) -> str:
    text = str(message_text or "").lower()
    needle = str(url or "").strip().lower()
    if not text or not needle:
        return ""
    index = text.find(needle)
    if index < 0:
        return ""
    start = max(0, index - 180)
    end = min(len(text), index + len(needle) + 180)
    return text[start:end]


def _link_context_has_report_cta(
    *,
    link_context: str,
    title_tokens: set[str],
) -> bool:
    context = str(link_context or "").casefold()
    if not context:
        return False
    cta_markers = {
        "download now",
        "download the report",
        "download your",
        "get the report",
        "access the report",
    }
    if any(marker in context for marker in cta_markers):
        return True
    return bool(
        title_tokens
        and title_tokens & _meaningful_tokens(context)
        and any(marker in context for marker in _REPORT_LINK_MARKERS)
    )


def _host_matches_source(*, host: str, source_host: str) -> bool:
    normalized_host = str(host or "").strip().lower().removeprefix("www.")
    normalized_source_host = (
        str(source_host or "").strip().lower().removeprefix("www.")
    )
    if not normalized_host or not normalized_source_host:
        return False
    return normalized_host == normalized_source_host or normalized_host.endswith(
        f".{normalized_source_host}"
    )


def _meaningful_tokens(value: str) -> set[str]:
    tokens = {
        token
        for token in re.split(r"[^a-z0-9]+", str(value or "").lower())
        if len(token) >= 4
    }
    return tokens - {"http", "https", "www", "com", "report", "download"}


def _is_absolute_http_url(url: str) -> bool:
    parsed = urlsplit(str(url or "").strip())
    return parsed.scheme in {"http", "https"} and bool(parsed.netloc)


__all__ = ["build_mailbox_query_terms", "select_mail_report_link_candidates"]
