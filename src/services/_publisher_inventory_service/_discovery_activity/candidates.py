from __future__ import annotations

import html
from urllib.parse import urljoin, urlsplit

from src.contracts.publisher_inventory import PublisherInventoryRawCandidate
from src.services._publisher_inventory_service._discovery_activity.constants import (
    _COMPONENT_LINK_WITH_HEADER_PATTERNS,
    _EMBEDDED_HEADLINE_RE,
    _EMBEDDED_HREF_RE,
    _NEGATIVE_PATH_MARKERS,
    _PAGINATION_LABELS,
    _REPORT_KEYWORDS,
    _SOCIAL_HOST_MARKERS,
    _STRONG_REPORT_KEYWORDS,
    _WEAK_REPORT_KEYWORDS,
)
from src.services._publisher_inventory_service._discovery_activity.titles import (
    _fallback_title_from_url,
    _is_generic_icon_label,
    _is_generic_insights_hub_title,
    _looks_like_human_report_title,
    _normalize_text,
    _select_anchor_title,
)
from src.services._publisher_inventory_service._discovery_activity.urls import (
    _is_inventory_article_path,
    _is_inventory_topic_hub_path,
    _is_inventory_type_archive_path,
    _is_reports_hub_path,
    _is_root_or_locale_home,
    _is_same_inventory_domain,
    _is_section_landing_page,
    _normalize_absolute_url,
    _page_query_value,
    _requires_origin_host_recovery,
)

def _resolve_next_page_url(
    *,
    current_page_url: str,
    page_number: int,
    anchors: list[dict[str, str]],
    rel_next_hrefs: list[str],
) -> str | None:
    for href in rel_next_hrefs:
        normalized = _normalize_absolute_url(urljoin(current_page_url, href))
        if normalized and normalized != current_page_url:
            return normalized
    numeric_candidates: list[tuple[int, str]] = []
    for anchor in anchors:
        href = str(anchor.get("href", "")).strip()
        title = _normalize_text(anchor.get("text", ""))
        rel = str(anchor.get("rel", "")).lower()
        normalized = _normalize_absolute_url(urljoin(current_page_url, href))
        if not normalized or normalized == current_page_url:
            continue
        if "next" in rel or title.casefold() in _PAGINATION_LABELS:
            return normalized
        page_value = _page_query_value(normalized)
        if page_value is not None and page_value > page_number:
            numeric_candidates.append((page_value, normalized))
    if not numeric_candidates:
        return None
    numeric_candidates.sort(key=lambda item: item[0])
    return numeric_candidates[0][1]

def _extract_candidates_from_html(
    *,
    anchors: list[dict[str, str]],
    page_url: str,
    page_number: int,
    next_page_url: str | None,
    origin_url: str | None = None,
    page_title: str = "",
    active_tab_label: str | None = None,
    archive_surface: bool = False,
    provenance: str | None = None,
) -> list[PublisherInventoryRawCandidate]:
    candidates: list[PublisherInventoryRawCandidate] = []
    seen_urls: set[str] = set()
    join_base_url = page_url
    if origin_url and _requires_origin_host_recovery(
        page_url=page_url,
        normalized_url=origin_url,
    ):
        join_base_url = origin_url
    if _should_include_page_url_as_candidate(
        page_url=page_url,
        origin_url=origin_url,
        page_title=page_title,
        archive_surface=archive_surface,
    ):
        seen_urls.add(page_url)
        pdf_url = page_url if page_url.lower().endswith(".pdf") else None
        candidates.append(
            PublisherInventoryRawCandidate(
                schema_version="1.0",
                url=page_url,
                title=page_title or _fallback_title_from_url(page_url),
                source_page_url=page_url,
                discovered_on_page_number=page_number,
                pdf_url=pdf_url,
                published_at_text=None,
                provenance=provenance,
                confidence=None,
            )
        )
    for anchor in anchors:
        href = str(anchor.get("href", "")).strip()
        if not href:
            continue
        absolute_url = _normalize_absolute_url(urljoin(join_base_url, href))
        if not absolute_url or absolute_url in seen_urls:
            continue
        title = _select_anchor_title(anchor)
        if not _looks_like_report_candidate(
            absolute_url=absolute_url,
            title=title,
            page_url=page_url,
            next_page_url=next_page_url,
            origin_url=origin_url,
            page_title=page_title,
            active_tab_label=active_tab_label,
            archive_surface=archive_surface,
        ):
            continue
        seen_urls.add(absolute_url)
        pdf_url = absolute_url if absolute_url.lower().endswith(".pdf") else None
        candidates.append(
            PublisherInventoryRawCandidate(
                schema_version="1.0",
                url=absolute_url,
                title=title or _fallback_title_from_url(absolute_url),
                source_page_url=page_url,
                discovered_on_page_number=page_number,
                pdf_url=pdf_url,
                published_at_text=None,
                provenance=provenance,
                confidence=None,
            )
        )
    return candidates

def _extract_component_link_anchors(
    *,
    html_text: str,
    page_url: str,
) -> list[dict[str, str]]:
    anchors: list[dict[str, str]] = []
    seen_urls: set[str] = set()
    normalized_page_url = _normalize_absolute_url(page_url) or page_url
    for pattern in _COMPONENT_LINK_WITH_HEADER_PATTERNS:
        for match in pattern.finditer(str(html_text or "")):
            link_payload = html.unescape(str(match.group("link") or "")).replace(
                "\\/", "/"
            )
            header_payload = html.unescape(str(match.group("header") or "")).replace(
                "\\/", "/"
            )
            href_match = _EMBEDDED_HREF_RE.search(link_payload)
            if href_match is None:
                continue
            absolute_url = _normalize_absolute_url(
                urljoin(normalized_page_url, str(href_match.group("href") or ""))
            )
            if not absolute_url or absolute_url in seen_urls:
                continue
            headline_match = _EMBEDDED_HEADLINE_RE.search(header_payload)
            title = (
                _normalize_text(str(headline_match.group("headline") or ""))
                if headline_match is not None
                else _fallback_title_from_url(absolute_url)
            )
            seen_urls.add(absolute_url)
            anchors.append(
                {
                    "href": absolute_url,
                    "rel": "",
                    "text": title,
                    "context_text": "",
                }
            )
    return anchors

def _should_include_page_url_as_candidate(
    *,
    page_url: str,
    origin_url: str | None,
    page_title: str,
    archive_surface: bool,
) -> bool:
    direct_page_keywords = (*_STRONG_REPORT_KEYWORDS, "trend", "trends", "barometer")
    normalized_url = _normalize_absolute_url(page_url)
    if not normalized_url:
        return False
    if archive_surface and not _looks_like_direct_report_detail_page(normalized_url):
        return False
    if _is_root_or_locale_home(normalized_url):
        return False
    if _is_section_landing_page(normalized_url):
        return False
    if _is_reports_hub_path(normalized_url):
        return False
    if _is_inventory_type_archive_path(normalized_url):
        return False
    if _is_inventory_topic_hub_path(normalized_url):
        return False
    lowered_url = normalized_url.casefold()
    if any(marker in lowered_url for marker in _NEGATIVE_PATH_MARKERS):
        return False
    path = urlsplit(normalized_url).path
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    leaf = segments[-1].rsplit(".", 1)[0].replace("-", " ").replace("_", " ").casefold()
    if leaf in {"report", "reports", "research", "resources", "insights"}:
        return False
    combined_text = " ".join(
        part
        for part in (
            lowered_url,
            _normalize_text(page_title).casefold(),
            _normalize_text(origin_url or "").casefold(),
        )
        if part
    )
    if any(keyword in combined_text for keyword in direct_page_keywords):
        return True
    return False

def _looks_like_direct_report_detail_page(url: str) -> bool:
    normalized_url = _normalize_absolute_url(url)
    if not normalized_url:
        return False
    parsed = urlsplit(normalized_url)
    path = parsed.path.casefold()
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    if leaf in {"report", "reports", "library"} or leaf.isdigit():
        return False
    if "/report-library/" in path and "report" in leaf:
        return True
    if "/report_pages/" in path:
        return True
    leaf_text = leaf.replace("-", " ").replace("_", " ")
    leaf_tokens = [token for token in leaf_text.split() if token]
    if len(leaf_tokens) < 3:
        return False
    if any(keyword in leaf_text for keyword in _STRONG_REPORT_KEYWORDS):
        return True
    return False

def _candidate_url_signature(
    candidates: list[PublisherInventoryRawCandidate],
) -> tuple[str, ...]:
    return tuple(
        sorted(
            {
                _normalize_absolute_url(candidate.url) or candidate.url
                for candidate in candidates
                if _normalize_absolute_url(candidate.url) or candidate.url
            }
        )
    )

def _anchor_fingerprint(
    anchors: list[dict[str, str]],
) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (
            _normalize_text(anchor.get("href", "")),
            _normalize_text(anchor.get("text", "")),
            _normalize_text(anchor.get("rel", "")),
        )
        for anchor in anchors
        if _normalize_text(anchor.get("href", ""))
    )

def _score_http_candidate_confidence(
    candidate: PublisherInventoryRawCandidate,
    *,
    page_url: str,
) -> float:
    normalized_url = _normalize_absolute_url(candidate.url)
    if not normalized_url:
        return 0.0
    if normalized_url.lower().endswith(".pdf"):
        return 1.0

    lowered_url = normalized_url.casefold()
    lowered_title = _normalize_text(candidate.title).casefold()
    page_host = str(urlsplit(page_url).hostname or "").strip().casefold()
    candidate_host = str(urlsplit(normalized_url).hostname or "").strip().casefold()

    score = 0.0
    if _is_same_inventory_domain(candidate_host, page_host):
        score += 0.10
    if any(keyword in lowered_url for keyword in _STRONG_REPORT_KEYWORDS):
        score += 0.45
    if any(keyword in lowered_title for keyword in _STRONG_REPORT_KEYWORDS):
        score += 0.35
    if any(keyword in lowered_url for keyword in _WEAK_REPORT_KEYWORDS):
        score += 0.05
    if any(keyword in lowered_title for keyword in _WEAK_REPORT_KEYWORDS):
        score += 0.05
    if _is_inventory_article_path(normalized_url):
        score += 0.05
    if _looks_like_human_report_title(candidate.title):
        score += 0.10
    if any(char.isdigit() for char in candidate.title):
        score += 0.05
    return max(0.0, min(round(score, 4), 1.0))

def _with_candidate_metadata(
    candidates: list[PublisherInventoryRawCandidate],
    *,
    provenance: str | None = None,
    confidence_by_url: dict[str, float] | None = None,
) -> list[PublisherInventoryRawCandidate]:
    updated: list[PublisherInventoryRawCandidate] = []
    confidence_by_url = confidence_by_url or {}
    for candidate in candidates:
        updated.append(
            PublisherInventoryRawCandidate(
                schema_version=candidate.schema_version,
                url=candidate.url,
                title=candidate.title,
                source_page_url=candidate.source_page_url,
                discovered_on_page_number=candidate.discovered_on_page_number,
                pdf_url=candidate.pdf_url,
                published_at_text=candidate.published_at_text,
                provenance=provenance or candidate.provenance,
                confidence=confidence_by_url.get(candidate.url, candidate.confidence),
            )
        )
    return updated

def _looks_like_report_candidate(
    *,
    absolute_url: str,
    title: str,
    page_url: str,
    next_page_url: str | None,
    origin_url: str | None = None,
    page_title: str = "",
    active_tab_label: str | None = None,
    archive_surface: bool = False,
) -> bool:
    if absolute_url == page_url or absolute_url == next_page_url:
        return False
    if absolute_url.startswith(("mailto:", "tel:", "javascript:")):
        return False
    lowered_url = absolute_url.casefold()
    candidate_host = str(urlsplit(absolute_url).hostname or "").strip().casefold()
    page_host = str(urlsplit(page_url).hostname or "").strip().casefold()
    origin_host = str(urlsplit(origin_url or "").hostname or "").strip().casefold()
    if any(marker in candidate_host for marker in _SOCIAL_HOST_MARKERS):
        return False
    if any(marker in lowered_url for marker in _NEGATIVE_PATH_MARKERS):
        return False
    lowered_title = title.casefold()
    if lowered_title in _PAGINATION_LABELS:
        return False
    if lowered_title in {"report", "reports"}:
        return False
    if lowered_title.startswith("view all "):
        return False
    if _is_generic_icon_label(lowered_title):
        return False
    if _is_section_landing_page(absolute_url):
        return False
    if _is_reports_hub_path(absolute_url):
        return False
    if _is_inventory_type_archive_path(absolute_url):
        return False
    if _is_inventory_topic_hub_path(absolute_url):
        return False
    if _is_root_or_locale_home(absolute_url):
        return False
    if absolute_url.lower().endswith(".pdf"):
        return True
    if archive_surface and (
        any(keyword in lowered_url for keyword in _STRONG_REPORT_KEYWORDS)
        or any(keyword in lowered_title for keyword in _STRONG_REPORT_KEYWORDS)
    ):
        return True
    if not (
        _is_same_inventory_domain(candidate_host, page_host)
        or (origin_host and _is_same_inventory_domain(candidate_host, origin_host))
    ):
        return False
    if _is_generic_insights_hub_title(lowered_title):
        return False
    if any(keyword in lowered_url for keyword in _STRONG_REPORT_KEYWORDS):
        return True
    if any(keyword in lowered_title for keyword in _STRONG_REPORT_KEYWORDS):
        return True
    if _is_inventory_article_path(absolute_url):
        return True
    if any(
        keyword in lowered_url for keyword in _WEAK_REPORT_KEYWORDS
    ) and _is_inventory_article_path(absolute_url):
        return True
    if any(
        keyword in lowered_title for keyword in _WEAK_REPORT_KEYWORDS
    ) and _is_inventory_article_path(absolute_url):
        return True
    if archive_surface and _is_same_inventory_domain(candidate_host, page_host):
        if title and len(title) >= 12 and _looks_like_human_report_title(title):
            return True
    if (
        archive_surface
        and _has_report_focused_surface_context(
            page_url=page_url,
            origin_url=origin_url,
            page_title=page_title,
            active_tab_label=active_tab_label,
        )
        and _is_same_inventory_domain(candidate_host, page_host)
    ):
        if title and len(title) >= 8 and _looks_like_human_report_title(title):
            return True
    if (
        title
        and len(title) >= 16
        and any(char.isdigit() for char in title)
        and _looks_like_human_report_title(title)
    ):
        return True
    return False

def _has_report_focused_surface_context(
    *,
    page_url: str,
    origin_url: str | None,
    page_title: str,
    active_tab_label: str | None,
) -> bool:
    parts = [
        str(page_url or "").strip().casefold(),
        str(origin_url or "").strip().casefold(),
        _normalize_text(page_title).casefold(),
        _normalize_text(active_tab_label or "").casefold(),
    ]
    combined = " ".join(part for part in parts if part)
    if not combined:
        return False
    return any(keyword in combined for keyword in _REPORT_KEYWORDS) or any(
        marker in combined
        for marker in (
            "resource library",
            "resource center",
            "knowledge hub",
            "library entries",
            "research",
        )
    )
