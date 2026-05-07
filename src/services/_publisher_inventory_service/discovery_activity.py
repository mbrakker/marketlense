"""Pure discovery activities extracted from the publisher inventory service.

This internal module keeps navigation control, candidate extraction, and
candidate-shape heuristics out of the public I/O entrypoint so the canonical
service boundary can focus on acquisition and external runtime coordination.
"""

from __future__ import annotations

import html
import re
from typing import Any, Mapping
from urllib.parse import parse_qs, urljoin, urlsplit

from src.contracts.publisher_inventory import PublisherInventoryRawCandidate
from src.utils.url_utils import normalize_url

_REPORT_KEYWORDS = (
    "report",
    "reports",
    "insight",
    "insights",
    "study",
    "research",
    "ebook",
    "whitepaper",
    "guide",
    "survey",
    "trend",
    "playbook",
    "forecast",
    "outlook",
    "benchmark",
)
_STRONG_REPORT_KEYWORDS = (
    "report",
    "reports",
    "study",
    "research",
    "ebook",
    "whitepaper",
    "guide",
    "survey",
    "playbook",
    "forecast",
    "outlook",
    "benchmark",
)
_WEAK_REPORT_KEYWORDS = (
    "insight",
    "insights",
    "trend",
)
_PAGINATION_LABELS = {
    "next",
    "next page",
    "older",
    "older posts",
    "more",
    "load more",
    ">",
    ">>",
    "»",
}
_NEGATIVE_PATH_MARKERS = (
    "/tag/",
    "/tags/",
    "/category/",
    "/categories/",
    "/author/",
    "/search",
    "/login",
    "/privacy",
    "/contact",
    "/about",
)
_SOCIAL_HOST_MARKERS = (
    "facebook.com",
    "linkedin.com",
    "twitter.com",
    "x.com",
    "instagram.com",
    "youtube.com",
    "tiktok.com",
)
_GENERIC_CTA_LABELS = {
    "read now",
    "download now",
    "learn more",
    "read report",
    "download report",
    "view report",
}
_REPORT_FOCUSED_TAB_MARKERS = (
    "report",
    "reports",
    "research",
    "white paper",
    "whitepaper",
    "ebook",
    "study",
    "benchmark",
    "insight",
    "insights",
)
_COMPONENT_LINK_WITH_HEADER_PATTERNS = (
    re.compile(
        r'link="(?P<link>[^"]*href&quot;:&quot;[^"]+)"[^>]*?teaserHeader="(?P<header>[^"]*headline&quot;:&quot;[^"]+)"',
        re.IGNORECASE | re.DOTALL,
    ),
    re.compile(
        r'teaserHeader="(?P<header>[^"]*headline&quot;:&quot;[^"]+)"[^>]*?link="(?P<link>[^"]*href&quot;:&quot;[^"]+)"',
        re.IGNORECASE | re.DOTALL,
    ),
)
_EMBEDDED_HREF_RE = re.compile(r'"href"\s*:\s*"(?P<href>[^"]+)"', re.IGNORECASE)
_EMBEDDED_HEADLINE_RE = re.compile(
    r'"headline"\s*:\s*"(?P<headline>[^"]+)"',
    re.IGNORECASE,
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


def _should_follow_report_listing(
    normalized_url: str,
    state: Any,
) -> bool:
    host = str(urlsplit(normalized_url).hostname or "").casefold()
    if "gfk-media-measurement.com" not in host:
        if not state.report_link_url:
            return False
        if _normalize_absolute_url(state.report_link_url) == _normalize_absolute_url(
            state.page_url
        ):
            return False
        if not _looks_like_report_listing_route_url(state.report_link_url):
            return False
        return not _is_archive_surface(state)
    path = str(urlsplit(normalized_url).path or "").casefold()
    if "/insights/report/" in path:
        return False
    if state.has_report_filter and state.has_apply_button:
        return False
    return bool(state.report_link_url)


def _should_expand_archive_library(
    state: Any,
    page_candidates: list[PublisherInventoryRawCandidate],
) -> bool:
    if state.load_more_labels or state.has_pagination_next:
        return False
    if state.page_total_hint and state.page_total_hint > 1:
        return False
    if state.result_range_total and state.result_range_total > max(
        len(page_candidates), 0
    ):
        return False
    if len(page_candidates) > 3:
        return False
    if _looks_like_report_listing_route_url(state.page_url):
        return False
    if not (
        _is_archive_surface(state)
        or _has_report_focused_surface_context(
            page_url=state.page_url,
            origin_url=state.page_url,
            page_title=state.page_title,
            active_tab_label=state.active_tab_label,
        )
    ):
        return False
    return True


def _should_apply_report_filter(
    normalized_url: str,
    state: Any,
) -> bool:
    _ = normalized_url
    return state.has_report_filter


def _should_traverse_tabs(
    normalized_url: str,
    state: Any,
) -> bool:
    host = str(urlsplit(normalized_url).hostname or "").casefold()
    return "salesforce.com" in host and len(state.tab_labels) > 1


def _select_tab_labels_for_traversal(
    normalized_url: str,
    state: Any,
) -> list[str]:
    labels = [
        _normalize_text(label) for label in state.tab_labels if _normalize_text(label)
    ]
    if not labels:
        return []
    unique_labels: list[str] = []
    seen_labels: set[str] = set()
    for label in labels:
        normalized_label = label.casefold()
        if normalized_label in seen_labels:
            continue
        seen_labels.add(normalized_label)
        unique_labels.append(label)
    preferred_labels = [
        label
        for label in unique_labels
        if any(marker in label.casefold() for marker in _REPORT_FOCUSED_TAB_MARKERS)
    ]
    if preferred_labels:
        return preferred_labels
    if _should_traverse_tabs(normalized_url, state):
        return unique_labels
    return []


def _is_archive_surface(state: Any) -> bool:
    substantive_anchor_count = sum(
        1
        for anchor in state.anchors
        if len(_normalize_text(anchor.get("text", ""))) >= 18
        and _looks_like_human_report_title(_normalize_text(anchor.get("text", "")))
    )
    return bool(
        state.load_more_labels
        or state.has_pagination_next
        or (state.page_total_hint and state.page_total_hint > 1)
        or (state.result_range_total and state.result_range_total > 0)
        or len(state.tab_labels) > 1
        or len(state.anchors) >= 12
        or substantive_anchor_count >= 3
    )


def _requires_archive_surface_recovery(
    *,
    state: Any,
    page_candidates: list[PublisherInventoryRawCandidate],
    normalized_url: str,
) -> bool:
    current_url = _normalize_absolute_url(state.page_url)
    origin_url = _normalize_absolute_url(normalized_url)
    if not current_url or not origin_url or current_url == origin_url:
        return False
    if _is_archive_surface(state):
        return False
    return len(page_candidates) < 3


def _is_terminal_results_page(state: Any) -> bool:
    if (
        state.page_index_hint is not None
        and state.page_total_hint is not None
        and state.page_total_hint > 0
        and state.page_index_hint >= state.page_total_hint
    ):
        return True
    if state.result_range_end is None or state.result_range_total is None:
        return False
    return (
        state.result_range_total > 0
        and state.result_range_end >= state.result_range_total
    )


def _needs_additional_hydration(
    state: Any,
    *,
    page_candidates: list[PublisherInventoryRawCandidate],
    next_page_url: str | None,
) -> bool:
    return (
        not state.load_more_labels
        and not state.has_pagination_next
        and not next_page_url
        and len(page_candidates) < 5
    )


def _rendered_state_anchor_fingerprint(state: Any) -> tuple[tuple[str, str, str], ...]:
    return tuple(
        (
            _normalize_text(anchor.get("href", "")),
            _normalize_text(anchor.get("text", "")),
            _normalize_text(anchor.get("rel", "")),
        )
        for anchor in state.anchors
        if _normalize_text(anchor.get("href", ""))
    )


def _is_exhausted_inert_load_more(
    *,
    previous_state: Any,
    stalled_state: Any,
) -> bool:
    if stalled_state.page_url != previous_state.page_url:
        return False
    if _rendered_state_anchor_fingerprint(
        stalled_state
    ) != _rendered_state_anchor_fingerprint(previous_state):
        return False
    if (
        stalled_state.result_range_end != previous_state.result_range_end
        or stalled_state.result_range_total != previous_state.result_range_total
    ):
        return False
    if stalled_state.has_pagination_next:
        return False
    previous_candidates = {
        candidate.url
        for candidate in _extract_candidates_from_html(
            anchors=previous_state.anchors,
            page_url=previous_state.page_url,
            page_number=1,
            next_page_url=None,
        )
    }
    stalled_candidates = {
        candidate.url
        for candidate in _extract_candidates_from_html(
            anchors=stalled_state.anchors,
            page_url=stalled_state.page_url,
            page_number=1,
            next_page_url=None,
        )
    }
    return stalled_candidates == previous_candidates


def _build_browser_route_summary(
    *,
    normalized_url: str,
    pages: list[Any],
    metrics: Any,
    used_tabs: bool,
    bounded_by_pagination_limit: bool = False,
) -> str:
    host = str(urlsplit(normalized_url).hostname or "").strip().lower()
    steps = [
        f"Rendered {host} in browser and extracted {len(pages)} inventory state(s)."
    ]
    if metrics.cookies_dismissed:
        steps.append(f"Dismissed cookie banners {metrics.cookies_dismissed} time(s).")
    if metrics.report_route_clicks:
        steps.append("Followed the report listing route before extraction.")
    if metrics.archive_expansion_clicks:
        steps.append(
            f"Expanded archive surfaces {metrics.archive_expansion_clicks} time(s)."
        )
    if metrics.report_filter_applied:
        steps.append("Applied the report format filter.")
    if used_tabs and metrics.tab_clicks:
        steps.append(f"Traversed {metrics.tab_clicks + 1} tabbed publisher section(s).")
    if metrics.load_more_clicks:
        steps.append(
            f"Expanded load-more pagination {metrics.load_more_clicks} time(s)."
        )
    if metrics.button_pagination_clicks:
        steps.append(
            f"Clicked button pagination {metrics.button_pagination_clicks} time(s)."
        )
    if metrics.next_page_visits:
        steps.append(
            f"Visited {metrics.next_page_visits} additional pagination URL(s)."
        )
    if getattr(metrics, "nested_scroll_probes", 0):
        surface = str(getattr(metrics, "scroll_surface", "nested_container")).strip()
        probe_count = int(getattr(metrics, "nested_scroll_probes", 0))
        steps.append(
            f"Probed {surface.replace('_', ' ')} scroll surfaces "
            f"{probe_count} time(s)."
        )
    if bounded_by_pagination_limit:
        steps.append(
            "Stopped at the configured pagination limit after collecting a bounded "
            "candidate set."
        )
    return " ".join(steps)


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


def _is_generic_icon_label(lowered_title: str) -> bool:
    token = str(lowered_title or "").strip()
    return (
        token.startswith("02_elements/")
        or token.startswith(".st")
        or token in {"close", "arrowright", "arrowleft"}
    )


def _looks_like_human_report_title(title: str) -> bool:
    token = str(title or "").strip()
    if not token:
        return False
    if any(char in token for char in {"{", "}", "<", ">", "\\", "/", "_"}):
        return False
    alpha_count = sum(1 for char in token if char.isalpha())
    return alpha_count >= 3


def _is_generic_insights_hub_title(lowered_title: str) -> bool:
    if not lowered_title or not lowered_title.endswith(" insights"):
        return False
    stem = lowered_title[: -len(" insights")].strip()
    if not stem:
        return False
    return all(char.isalpha() or char in {" ", "&", "-"} for char in stem)


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


def _normalize_text(value: str) -> str:
    return " ".join(str(value or "").split()).strip()


def _select_anchor_title(item: Mapping[str, object]) -> str:
    text = _normalize_text(str(item.get("text") or ""))
    heading_text = _normalize_text(str(item.get("heading_text") or ""))
    aria_label = _normalize_text(str(item.get("aria_label") or ""))
    title_attr = _normalize_text(str(item.get("title_attr") or ""))
    img_alt = _normalize_text(str(item.get("img_alt") or ""))
    context_text = _normalize_text(str(item.get("context_text") or ""))
    if heading_text:
        if not text or text.casefold() in _GENERIC_CTA_LABELS:
            return heading_text
        lowered_text = text.casefold()
        lowered_heading = heading_text.casefold()
        if lowered_heading == lowered_text:
            return heading_text
        if lowered_heading in lowered_text and len(text) >= len(heading_text) + 24:
            return heading_text
    if text and text.casefold() not in _GENERIC_CTA_LABELS:
        return text
    if aria_label and aria_label.casefold() not in _GENERIC_CTA_LABELS:
        return aria_label
    if title_attr and title_attr.casefold() not in _GENERIC_CTA_LABELS:
        return title_attr
    if img_alt and img_alt.casefold() not in _GENERIC_CTA_LABELS:
        return img_alt
    context_title = _card_context_title(context_text)
    if context_title:
        return context_title
    return heading_text or aria_label or title_attr or img_alt or text


def _card_context_title(context_text: str) -> str:
    normalized = _normalize_text(context_text)
    if not normalized:
        return ""
    lowered = normalized.casefold()
    for label in sorted(_GENERIC_CTA_LABELS, key=len, reverse=True):
        if lowered.endswith(label):
            normalized = normalized[: -len(label)].rstrip(" -:>|")
            lowered = normalized.casefold()
            break
    if len(normalized) <= 180:
        return normalized
    return normalized[:180].rsplit(" ", 1)[0].rstrip(" -:>|")


def _fallback_title_from_url(url: str) -> str:
    path = urlsplit(url).path.rsplit("/", 1)[-1]
    token = path.rsplit(".", 1)[0].replace("-", " ").replace("_", " ").strip()
    return _normalize_text(token) or url


def _normalize_absolute_url(url: str) -> str:
    normalized_url = normalize_url(url)
    parts = urlsplit(normalized_url)
    if parts.scheme not in {"http", "https"} or not parts.netloc:
        return ""
    return normalized_url
