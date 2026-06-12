from __future__ import annotations

from urllib.parse import parse_qs, urlsplit

from src.utils.url_utils import normalize_url

def _looks_like_report_listing_route_url(url: str) -> bool:
    path = str(urlsplit(url).path or "").strip().casefold().rstrip("/")
    if not path:
        return False
    if _is_root_or_locale_home(url) or _is_section_landing_page(url):
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    archive_tail_markers = {
        "ebooks",
        "guides-whitepapers",
        "livres-blancs",
        "publication",
        "publications",
        "report",
        "reports",
        "research",
        "resources",
        "resource-library",
        "knowledge-hub",
        "library",
        "white-papers",
        "whitepaper",
        "whitepapers",
    }
    return segments[-1] in archive_tail_markers

def _is_same_inventory_domain(candidate_host: str, page_host: str) -> bool:
    if not candidate_host or not page_host:
        return False
    candidate_apex = _apex_domain(candidate_host)
    page_apex = _apex_domain(page_host)
    return bool(candidate_apex and page_apex and candidate_apex == page_apex)

def _requires_origin_host_recovery(*, page_url: str, normalized_url: str) -> bool:
    normalized_page_url = _normalize_absolute_url(page_url)
    normalized_origin_url = _normalize_absolute_url(normalized_url)
    if not normalized_page_url or not normalized_origin_url:
        return False
    if normalized_page_url == normalized_origin_url:
        return False
    page_host = str(urlsplit(normalized_page_url).hostname or "").strip().casefold()
    origin_host = str(urlsplit(normalized_origin_url).hostname or "").strip().casefold()
    return bool(
        page_host
        and origin_host
        and _apex_domain(page_host) != _apex_domain(origin_host)
    )

def _apex_domain(host: str) -> str:
    parts = [part for part in str(host or "").strip().casefold().split(".") if part]
    if len(parts) < 2:
        return ""
    return ".".join(parts[-2:])

def _is_section_landing_page(url: str) -> bool:
    path = str(urlsplit(url).path or "").strip().casefold().rstrip("/")
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if segments == ["insights"]:
        return True
    if len(segments) == 2 and segments[1] == "insights":
        return True
    return False

def _is_inventory_article_path(url: str) -> bool:
    path = str(urlsplit(url).path or "").strip().casefold().rstrip("/")
    if not path.startswith("/insights/"):
        return False
    return not _is_section_landing_page(url)

def _is_inventory_type_archive_path(url: str) -> bool:
    segments = [
        segment
        for segment in str(urlsplit(url).path or "")
        .strip()
        .casefold()
        .rstrip("/")
        .split("/")
        if segment
    ]
    if len(segments) >= 3 and segments[0] == "insights" and segments[1] == "type":
        return True
    if len(segments) >= 4 and segments[1] == "insights" and segments[2] == "type":
        return True
    return False

def _is_inventory_topic_hub_path(url: str) -> bool:
    path = str(urlsplit(url).path or "").strip().casefold().rstrip("/")
    return "/insights/topic/" in path

def _is_reports_hub_path(url: str) -> bool:
    segments = [
        segment
        for segment in str(urlsplit(url).path or "")
        .strip()
        .casefold()
        .rstrip("/")
        .split("/")
        if segment
    ]
    return len(segments) >= 2 and "insights" in segments and segments[-1] == "reports"

def _is_root_or_locale_home(url: str) -> bool:
    segments = [
        segment
        for segment in str(urlsplit(url).path or "")
        .strip()
        .casefold()
        .rstrip("/")
        .split("/")
        if segment
    ]
    if not segments:
        return True
    return len(segments) == 1 and _looks_like_locale_segment(segments[0])

def _looks_like_locale_segment(segment: str) -> bool:
    token = str(segment or "").strip().casefold()
    if not token:
        return False
    if len(token) == 2 and token.isalpha():
        return True
    parts = token.split("-")
    return (
        len(parts) == 2
        and all(part.isalpha() for part in parts)
        and 2 <= len(parts[0]) <= 3
        and 2 <= len(parts[1]) <= 3
    )

def _page_query_value(url: str) -> int | None:
    query = parse_qs(urlsplit(url).query)
    for key in ("page", "paged", "p"):
        values = query.get(key)
        if not values:
            continue
        try:
            return int(str(values[0]).strip())
        except (TypeError, ValueError):
            return None
    return None

def _positive_int_or_none(value: object) -> int | None:
    if isinstance(value, bool):
        return int(value) if value > 0 else None
    if not isinstance(value, (int, float, str, bytes, bytearray)):
        return None
    try:
        parsed = int(value)
    except (TypeError, ValueError):
        return None
    return parsed if parsed > 0 else None

def _normalize_absolute_url(url: str) -> str:
    normalized_url = normalize_url(url)
    parts = urlsplit(normalized_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return normalized_url
