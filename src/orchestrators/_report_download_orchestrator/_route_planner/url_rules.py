from __future__ import annotations
import logging
import re
from urllib.parse import parse_qs, unquote, urlsplit
from src.contracts.browser_download import (
    BrowserDownloadRouteStep,
)

logger = logging.getLogger("market_lense.report_download_route_planner")
_BROWSER_DISCOVERY_PROVENANCES = {
    "browser_dom",
    "browser_rendered_html_supplement",
}
_PDF_FIRST_DISCOVERY_PROVENANCES = {
    "direct_pdf_source",
}
_TRACKER_HOST_MARKERS = {
    "lnk",
    "trk",
    "click",
    "go",
    "email",
    "hubspot",
    "pardot",
    "marketo",
}
_TRACKER_SHORT_PATH_MARKERS = {
    "go",
    "lnk",
    "trk",
}
_LISTING_PATH_MARKERS = {
    "insights",
    "reports",
    "research",
    "resources",
    "publications",
    "library",
}
_EDITORIAL_NON_REPORT_MARKERS = {
    "blog",
    "news",
    "press",
    "case-study",
    "case_study",
    "webinar",
}
_EDITORIAL_REPORT_MARKERS = {
    "report",
    "reports",
    "guide",
    "guides",
    "insight",
    "insights",
    "playbook",
    "research",
    "analysis",
    "study",
    "survey",
    "trend",
    "trends",
    "whitepaper",
    "whitepapers",
}
_BROWSER_TO_HTTP_RECOVERY_CLASS = "browser_to_http_pdf_probe"
_DIRECT_PDF_RECOVERY_CLASS = "direct_pdf_probe"
_HTTP_PDF_RECOVERY_CLASS = "http_pdf_probe"
_REPORT_DETAIL_SIGNAL_MARKERS = {
    "benchmark",
    "download",
    "ebook",
    "e-book",
    "guide",
    "market",
    "outlook",
    "playbook",
    "predictions",
    "report",
    "research",
    "study",
    "survey",
    "trend",
    "trends",
    "whitepaper",
    "white paper",
}
_EMAIL_GATE_PATH_MARKERS = {
    "gated-content-form",
    "download",
    "downloads",
    "ebook",
    "ebooks",
    "whitepaper",
    "whitepapers",
    "asset",
    "assets",
    "register",
    "form",
}
_EMAIL_GATE_PARENT_SEGMENTS = {
    "report",
    "reports",
    "resources",
}
_EMAIL_GATE_DETAIL_TITLE_MARKERS = {
    "benchmark",
    "ebook",
    "e-book",
    "guide",
    "outlook",
    "predictions",
    "report",
    "research",
    "study",
    "trends",
    "whitepaper",
    "white paper",
}
_ONSITE_LONGREAD_SEGMENTS = {
    "insight",
    "insights",
    "research",
    "analysis",
    "survey",
    "outlook",
}
_DIRECT_ONSITE_REPORT_SEGMENTS = {
    "guide",
    "guides",
    "insight",
    "playbook",
    "playbooks",
    "research",
    "analysis",
    "survey",
    "outlook",
}
_DIRECT_ONSITE_REPORT_PATH_PHRASES = {
    "year-in-review",
}
_DIRECT_ONSITE_DIGITAL_YEAR_SEGMENT_RX = re.compile(
    r"^(?:digital|global-digital)-20\d{2}(?:-|$)"
)
_ONSITE_EXCLUDED_SEGMENTS = {
    "resources",
    "reports",
    "report",
    "download",
    "downloads",
    "ebook",
    "whitepaper",
    "whitepapers",
    "asset",
    "assets",
    "form",
    "register",
}
_TRACKER_QUERY_KEYS = (
    "url",
    "target",
    "dest",
    "destination",
    "redirect",
    "redirect_url",
    "redirect_uri",
    "u",
    "r",
)


def _clean_string_list(values: list[str]) -> list[str]:
    cleaned: list[str] = []
    seen: set[str] = set()
    for value in values:
        token = str(value or "").strip()
        if not token:
            continue
        marker = token.casefold()
        if marker in seen:
            continue
        seen.add(marker)
        cleaned.append(token)
    return cleaned


def _looks_like_pdf(url: str) -> bool:
    return (
        str(urlsplit(str(url or "").strip()).path or "")
        .strip()
        .lower()
        .endswith(".pdf")
    )


def _looks_like_listing_url(url: str) -> bool:
    path = str(urlsplit(str(url or "").strip()).path or "").strip().lower()
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False

    def is_listing_segment(segment: str) -> bool:
        return any(marker in segment for marker in _LISTING_PATH_MARKERS)

    if not any(is_listing_segment(segment) for segment in segments):
        return False
    last_segment = segments[-1]
    if len(segments) == 1:
        return is_listing_segment(last_segment)
    if is_listing_segment(last_segment):
        return True
    if len(segments) == 2 and is_listing_segment(segments[0]):
        slug_token_count = len([token for token in last_segment.split("-") if token])
        return slug_token_count < 2
    return False


def _looks_like_tracker_url(url: str) -> bool:
    parsed = urlsplit(str(url or "").strip())
    hostname = str(parsed.hostname or "").strip().lower()
    path = str(parsed.path or "").strip().lower()
    query = str(parsed.query or "").strip().lower()
    host_labels = [label for label in hostname.split(".") if label]
    tracker_host = any(label in _TRACKER_HOST_MARKERS for label in host_labels)
    if tracker_host:
        return True
    path_query_tokens = _tracker_path_query_tokens(path=path, query=query)
    for marker in _TRACKER_HOST_MARKERS:
        if marker in _TRACKER_SHORT_PATH_MARKERS:
            if marker in path_query_tokens:
                return True
            continue
        if marker in path or marker in query:
            return True
    return False


def _tracker_path_query_tokens(*, path: str, query: str) -> set[str]:
    text = f"{path} {query}"
    return {token for token in re.split(r"[^a-z0-9]+", text) if token}


def _extract_tracker_target_url(url: str) -> str | None:
    parsed = urlsplit(str(url or "").strip())
    if not parsed.query:
        return None
    query = parse_qs(parsed.query, keep_blank_values=False)
    for key in _TRACKER_QUERY_KEYS:
        values = query.get(key)
        if not values:
            continue
        candidate = unquote(str(values[0] or "").strip())
        if candidate.startswith("http://") or candidate.startswith("https://"):
            return candidate
    return None


def _classify_redirect_target(url: str | None) -> str:
    token = str(url or "").strip()
    if not token:
        return ""
    if _looks_like_pdf(token):
        return "redirect_to_pdf"
    if _looks_like_onsite_longread_url(token):
        return "redirect_to_onsite_report"
    lowered = str(urlsplit(token).path or "").strip().lower()
    if _path_has_email_gate_marker(lowered):
        return "redirect_to_email_gate"
    if any(marker in lowered for marker in _EDITORIAL_NON_REPORT_MARKERS):
        return "redirect_to_non_report"
    return ""


def _looks_like_editorial_report_url(url: str | None) -> bool:
    path = str(urlsplit(str(url or "").strip()).path or "").strip().lower()
    if not path or _looks_like_pdf(path):
        return False
    if any(marker in path for marker in _EDITORIAL_NON_REPORT_MARKERS):
        return False
    return any(marker in path for marker in _EDITORIAL_REPORT_MARKERS)


def _looks_like_onsite_longread_url(url: str | None) -> bool:
    parsed = urlsplit(str(url or "").strip())
    path = str(parsed.path or "").strip().lower()
    if not path or _looks_like_pdf(path):
        return False
    if any(marker in path for marker in _EDITORIAL_NON_REPORT_MARKERS):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    if any(segment in _ONSITE_EXCLUDED_SEGMENTS for segment in segments):
        return False
    if any(segment in _ONSITE_LONGREAD_SEGMENTS for segment in segments):
        return True
    return any(marker in path for marker in _EDITORIAL_REPORT_MARKERS)


def _looks_like_email_form_url(
    url: str | None,
    *,
    candidate_title: str = "",
    source_page_urls: list[str] | None = None,
) -> bool:
    path = str(urlsplit(str(url or "").strip()).path or "").strip().lower()
    if not path or _looks_like_pdf(path):
        return False
    if _path_has_email_gate_marker(path):
        return True
    if _looks_like_probable_gated_report_detail_url(
        path=path,
        candidate_title=candidate_title,
        source_page_urls=source_page_urls or [],
    ):
        return True
    if _looks_like_direct_onsite_report_url(url):
        return False
    return False


def _looks_like_direct_onsite_report_url(url: str | None) -> bool:
    parsed = urlsplit(str(url or "").strip())
    path = str(parsed.path or "").strip().lower()
    if not path or _looks_like_pdf(path):
        return False
    if _path_has_email_gate_marker(path):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    if _path_has_direct_onsite_report_phrase(path=path, segments=segments):
        return True
    if any(segment in _ONSITE_EXCLUDED_SEGMENTS for segment in segments):
        return False
    return any(
        segment in _DIRECT_ONSITE_REPORT_SEGMENTS
        or any(
            segment.startswith(f"{marker}-")
            for marker in _DIRECT_ONSITE_REPORT_SEGMENTS
        )
        for segment in segments
    )


def _path_has_direct_onsite_report_phrase(
    *,
    path: str,
    segments: list[str],
) -> bool:
    if any(phrase in path for phrase in _DIRECT_ONSITE_REPORT_PATH_PHRASES):
        return True
    if not ({"report", "reports"} & set(segments)):
        return False
    return any(
        _DIRECT_ONSITE_DIGITAL_YEAR_SEGMENT_RX.match(segment) is not None
        for segment in segments
    )


def _onsite_capture_route_steps(
    attempt_url: str | None,
) -> list[BrowserDownloadRouteStep]:
    target_url = str(attempt_url or "").strip()
    return [
        BrowserDownloadRouteStep(
            schema_version="1.0",
            index=0,
            action="extract",
            target_text=target_url,
            target_role="html",
            target_url=target_url,
            result="Capture the on-site report HTML when it is complete report content.",
            expected_evidence=[
                "long-form report text",
                "complete on-site report content",
            ],
            observed_evidence=[],
            verification_status="planned",
        )
    ]


def _path_has_email_gate_marker(path: str) -> bool:
    token = str(path or "").strip().lower()
    if not token:
        return False
    if "gated-content-form" in token:
        return True
    segments = [segment for segment in token.split("/") if segment]
    split_tokens = {part for part in re.split(r"[^a-z0-9]+", token) if part}
    for marker in _EMAIL_GATE_PATH_MARKERS:
        if marker == "gated-content-form":
            continue
        if marker in split_tokens:
            return True
        for segment in segments:
            if (
                segment == marker
                or segment.startswith(f"{marker}-")
                or segment.endswith(f"-{marker}")
            ):
                return True
    return False


def _looks_like_probable_gated_report_detail_url(
    *,
    path: str,
    candidate_title: str,
    source_page_urls: list[str],
) -> bool:
    segments = [segment for segment in str(path or "").split("/") if segment]
    if len(segments) < 2:
        return False
    split_tokens = {part for part in re.split(r"[^a-z0-9]+", str(path or "")) if part}
    title = str(candidate_title or "").strip().lower()
    title_has_asset_marker = any(
        marker in title for marker in _EMAIL_GATE_DETAIL_TITLE_MARKERS
    )
    slug_has_asset_marker = bool(
        split_tokens
        & {
            "benchmark",
            "ebook",
            "guide",
            "outlook",
            "predictions",
            "report",
            "research",
            "study",
            "trends",
            "whitepaper",
        }
    )
    source_path_text = " ".join(
        str(urlsplit(str(source_url or "").strip()).path or "").strip().lower()
        for source_url in source_page_urls
    )
    source_is_report_listing = any(
        segment in _EMAIL_GATE_PARENT_SEGMENTS
        for segment in re.split(r"[^a-z0-9]+", source_path_text)
        if segment
    )
    if (
        "resources" in segments
        and "reports" in segments
        and (title_has_asset_marker or slug_has_asset_marker)
    ):
        return True
    if (
        source_is_report_listing
        and title_has_asset_marker
        and slug_has_asset_marker
        and any(re.fullmatch(r"\d{4}", segment) for segment in segments)
    ):
        return True
    for index, segment in enumerate(segments[:-1]):
        if segment not in {"report", "reports"}:
            continue
        detail_slug = segments[index + 1]
        if not detail_slug or detail_slug in _LISTING_PATH_MARKERS:
            continue
        if title_has_asset_marker or slug_has_asset_marker:
            return True
        if source_is_report_listing and re.match(r"^\d{3,}", detail_slug):
            return True
    return False


__all__ = [
    "_clean_string_list",
    "_looks_like_pdf",
    "_looks_like_listing_url",
    "_looks_like_tracker_url",
    "_tracker_path_query_tokens",
    "_extract_tracker_target_url",
    "_classify_redirect_target",
    "_looks_like_editorial_report_url",
    "_looks_like_onsite_longread_url",
    "_looks_like_email_form_url",
    "_looks_like_direct_onsite_report_url",
    "_path_has_direct_onsite_report_phrase",
    "_onsite_capture_route_steps",
    "_path_has_email_gate_marker",
    "_looks_like_probable_gated_report_detail_url",
]
