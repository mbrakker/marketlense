"""Shared constants and normalization helpers for publisher screening.

This module owns deterministic marker lists, shared logging identity, and text
normalization helpers used by screening policy and LLM prompt preparation.
"""

from __future__ import annotations

import logging
import re
import unicodedata

logger = logging.getLogger(
    "market_lense.publisher_inventory_candidate_screening_generator"
)


_MAX_PROMPT_TITLE_LENGTH = 280


_FALLBACK_REPORT_TITLE_MARKERS = (
    "buyers guide",
    "buyer's guide",
    "guideline",
    "guidelines",
    "prediction",
    "predictions",
    "report",
    "reports",
    "rapport",
    "white paper",
    "whitepaper",
    "white papers",
    "whitepapers",
    "study",
    "studies",
    "survey",
    "surveys",
    "benchmark",
    "benchmarks",
    "outlook",
    "outlooks",
    "ebook",
    "ebooks",
    "guide",
    "guides",
    "playbook",
    "playbooks",
    "forecast",
    "forecasts",
    "outlook",
    "barometer",
    "barometre",
    "observatory",
    "observatoire",
    "index",
    "pulse",
    "scorecard",
    "trends",
    "trend",
    "research",
    "analysis",
    "fact sheet",
    "fact sheets",
    "atlas",
    "atlases",
    "barometer",
    "infographic",
    "note de conjoncture",
)


_FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS = (
    "annual report",
    "benchmark",
    "benchmarks",
    "buyers guide",
    "buyer's guide",
    "ebook",
    "ebooks",
    "forecast",
    "forecasts",
    "guide",
    "guides",
    "guideline",
    "guidelines",
    "index",
    "outlook",
    "outlooks",
    "playbook",
    "playbooks",
    "prediction",
    "predictions",
    "scorecard",
    "study",
    "studies",
    "survey",
    "surveys",
    "fact sheet",
    "fact sheets",
    "atlas",
    "barometer",
    "transparency report",
    "white paper",
    "whitepaper",
)


_FALLBACK_NON_REPORT_TITLE_MARKERS = (
    "analyst relations council",
    "cookie notice",
    "cookie policy",
    "privacy notice",
    "privacy policy",
    "code of conduct",
    "modern slavery",
    "gender pay",
    "tax strategy",
    "case study",
    "contact us",
    "join the panel",
    "publication archive",
    "property not found",
    "planned research",
    "page not found",
    "reprints",
    "all products",
    "award-winning experts",
    "accurate data",
    "real people",
    "pioneering tech",
    "binding corporate rules",
    "bcr summary",
    "gender equality index",
    "equality index",
    "index de l egalite",
    "index de l égalité",
    "egalite femmes hommes",
    "égalité femmes-hommes",
    "masterclass",
    "template",
    "templates",
    "training",
    "video",
    "webinar",
    "case studies",
    "customer story",
    "customer stories",
    "client story",
    "client stories",
)


_FALLBACK_NON_REPORT_URL_MARKERS = (
    "/article/",
    "/articles/",
    "/academy/",
    "/blog/",
    "/blogs/",
    "/case-study",
    "/case-studies/",
    "/case-studies",
    "/careers",
    "/contact",
    "/customer-story",
    "/customer-stories/",
    "/customer-stories",
    "/help/",
    "/login",
    "/news/",
    "/newsroom/",
    "/panel",
    "/press-release",
    "/press-releases/",
    "/products",
    "/privacy",
    "/registration/",
    "/reprints",
    "/cookie",
    "/modern-slavery",
    "/tax-strategy",
    "/code-of-conduct",
    "/training/",
    "/video",
    "/webinar",
    "academy.",
    "support.",
    "/hc/en-us/articles/",
)


_FALLBACK_REPORT_URL_MARKERS = (
    "/publication/",
    "/publications/",
    "/benchmark",
    "/benchmarks/",
    "/buyers-guide",
    "/buyers-guides/",
    "/barometer",
    "/data-report",
    "/data-reports/",
    "/ebook",
    "/ebooks/",
    "/fact-sheet",
    "/fact-sheets/",
    "/forecast",
    "/forecasts/",
    "/guide",
    "/guides/",
    "/industry-report",
    "/industry-reports/",
    "/lp/product-fact-sheet/",
    "/lp/report/",
    "/outlook",
    "/playbook",
    "/report/",
    "/reports/",
    "/reports_posts/",
    "/report_pages/",
    "/research/",
    "/study",
    "/studies/",
    "/survey",
    "/surveys/",
    "/trend",
    "/trends/",
    "/white-paper",
    "/whitepaper",
    "/whitepapers/",
)


_FALLBACK_REPORT_COLLECTION_SEGMENTS = {
    "all",
    "asset",
    "assets",
    "benchmark",
    "benchmarks",
    "ebook",
    "ebooks",
    "guide",
    "guides",
    "insights",
    "library",
    "playbook",
    "playbooks",
    "report",
    "reports",
    "research",
    "resource",
    "resources",
    "publication",
    "publications",
    "studies",
    "study",
    "survey",
    "surveys",
    "whitepaper",
    "whitepapers",
}


_FALLBACK_LISTING_QUERY_KEYS = (
    "category=",
    "page=",
    "pagenum=",
    "resource_type=",
    "tag=",
    "topic=",
    "type=",
)


_EDITORIAL_REPORT_URL_MARKERS = (
    "/article/",
    "/articles/",
    "/blog/",
    "/blogs/",
    "/news/",
    "/newsroom/",
    "/press-release",
    "/press-releases/",
)


_COLLECTION_ROOT_URL_TOKENS = {
    "all",
    "and",
    "article",
    "articles",
    "asset",
    "assets",
    "blog",
    "blogs",
    "center",
    "centre",
    "guide",
    "guides",
    "hub",
    "insight",
    "insights",
    "knowledge",
    "library",
    "publication",
    "publications",
    "report",
    "reports",
    "research",
    "resource",
    "resources",
    "study",
    "studies",
    "survey",
    "surveys",
    "topic",
    "topics",
    "whitepaper",
    "whitepapers",
}


_REPORT_CONTEXT_STOP_WORDS = {
    "a",
    "an",
    "and",
    "for",
    "from",
    "in",
    "of",
    "on",
    "our",
    "the",
    "to",
    "with",
}


_DIRECT_DETAIL_SOURCE_URL_MARKERS = (
    "/research-library/",
    "/report/",
    "/reports/",
    "/whitepaper/",
    "/whitepapers/",
    "/ebook/",
    "/ebooks/",
    "/study/",
    "/studies/",
    "/survey/",
    "/surveys/",
)


_EDITORIAL_NON_REPORT_URL_MARKERS = (
    "/ask/",
    "/help/",
    "/hc/en-us/articles/",
    "/support/",
    "/webinar",
    "support.",
)


_INFORMATIONAL_TITLE_PREFIXES = (
    "how ",
    "what ",
    "when ",
    "where ",
    "who ",
    "why ",
)


_GENERIC_CTA_TITLES = {
    "download now",
    "download report",
    "download the report",
    "get the report",
    "learn more",
    "read article",
    "read more",
    "read now",
    "read report",
    "view report",
}


_EDITORIAL_SPECIFIC_REPORT_TITLE_MARKERS = (
    "annual report",
    "atlas",
    "barometer",
    "benchmark",
    "benchmarks",
    "ebook",
    "ebooks",
    "fact sheet",
    "fact sheets",
    "forecast",
    "forecasts",
    "guideline",
    "guidelines",
    "outlook",
    "outlooks",
    "prediction",
    "predictions",
    "report",
    "reports",
    "study",
    "studies",
    "survey",
    "surveys",
    "white paper",
    "whitepaper",
)


_GENERIC_DUPLICATE_TITLE_FINGERPRINTS = {
    "",
    "download annual report",
    "download pdf",
    "download for free",
    "download now",
    "download report",
    "download the report",
    "ebook",
    "get the report",
    "guide",
    "learn more",
    "read article",
    "read more",
    "read now",
    "read report",
    "report",
    "reports",
    "view report",
    "white paper",
    "whitepaper",
}


_PUBLISHER_SUCCESS_ANALYST_MARKERS = (
    "gartner",
    "forrester",
    "omdia",
    "idc",
    "peak matrix",
    "marketscape",
    "magic quadrant",
    "quadrant",
    "wave",
)


_PUBLISHER_SUCCESS_HARD_PATTERNS = (
    re.compile(r"\bnamed\s+(?:a|an|the\s+)?leader\b"),
    re.compile(r"\bnames?\b.*\ba\s+leader\b"),
    re.compile(r"\brated\s+(?:a|an|the\s+)?leader\b"),
    re.compile(r"\brecogni[sz]ed\s+as\s+(?:a|an|the\s+)?leader\b"),
    re.compile(r"\btop[- ]rated\b"),
    re.compile(r"\btop ratings?\b"),
    re.compile(r"\bcustomer favorite\b"),
    re.compile(r"\bhighest[- ]designated leader\b"),
    re.compile(r"\bbrings home the gold\b"),
    re.compile(
        r"\b(?:earns?|receiv(?:e|es|ing)|wins?)\s+\d+\s+(?:exceptional[- ]rated\s+)?(?:gold\s+)?medals?\b"
    ),
    re.compile(r"\bgoes big\b"),
    re.compile(r"\bjust ask\b"),
    re.compile(r"\bearns?\s+top ratings?\b"),
    re.compile(r"\bleader in\b"),
    re.compile(r"\bleader for\b"),
)


def _normalize_title_fingerprint(title: str) -> str:
    token = unicodedata.normalize("NFKD", str(title or ""))
    normalized = "".join(
        char.casefold() if char.isalnum() or char.isspace() else " " for char in token
    )
    return " ".join(normalized.split()).strip()


def _contains_any_title_marker(title: str, markers: tuple[str, ...]) -> bool:
    normalized_title = _normalize_title_fingerprint(title)
    if not normalized_title:
        return False
    normalized_words = {
        _normalize_marker_word(token)
        for token in re.findall(r"[a-z0-9]+", normalized_title)
        if token
    }
    for marker in markers:
        normalized_marker = _normalize_title_fingerprint(marker)
        if not normalized_marker:
            continue
        if " " in normalized_marker:
            if normalized_marker in normalized_title:
                return True
            continue
        if _normalize_marker_word(normalized_marker) in normalized_words:
            return True
    return False


def _normalize_marker_word(token: str) -> str:
    normalized_token = str(token or "").strip().casefold()
    if len(normalized_token) <= 4:
        return normalized_token
    if normalized_token.endswith("ies"):
        return normalized_token[:-3] + "y"
    if normalized_token.endswith("s") and not normalized_token.endswith("ss"):
        return normalized_token[:-1]
    return normalized_token


def _publisher_reference_tokens(publisher_name: str) -> tuple[str, ...]:
    normalized_name = _normalize_title_fingerprint(publisher_name)
    if not normalized_name:
        return ()
    tokens = [token for token in normalized_name.split() if len(token) >= 4]
    unique_tokens: list[str] = []
    for token in [normalized_name, *tokens]:
        if token and token not in unique_tokens:
            unique_tokens.append(token)
    return tuple(unique_tokens)


def _truncate_prompt_text(value: str) -> str:
    normalized_value = " ".join(str(value or "").split()).strip()
    if len(normalized_value) <= _MAX_PROMPT_TITLE_LENGTH:
        return normalized_value
    return normalized_value[: _MAX_PROMPT_TITLE_LENGTH - 1].rstrip() + "…"


__all__ = [
    "logger",
    "_MAX_PROMPT_TITLE_LENGTH",
    "_FALLBACK_REPORT_TITLE_MARKERS",
    "_FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS",
    "_FALLBACK_NON_REPORT_TITLE_MARKERS",
    "_FALLBACK_NON_REPORT_URL_MARKERS",
    "_FALLBACK_REPORT_URL_MARKERS",
    "_FALLBACK_REPORT_COLLECTION_SEGMENTS",
    "_FALLBACK_LISTING_QUERY_KEYS",
    "_EDITORIAL_REPORT_URL_MARKERS",
    "_COLLECTION_ROOT_URL_TOKENS",
    "_REPORT_CONTEXT_STOP_WORDS",
    "_DIRECT_DETAIL_SOURCE_URL_MARKERS",
    "_EDITORIAL_NON_REPORT_URL_MARKERS",
    "_INFORMATIONAL_TITLE_PREFIXES",
    "_GENERIC_CTA_TITLES",
    "_EDITORIAL_SPECIFIC_REPORT_TITLE_MARKERS",
    "_GENERIC_DUPLICATE_TITLE_FINGERPRINTS",
    "_PUBLISHER_SUCCESS_ANALYST_MARKERS",
    "_PUBLISHER_SUCCESS_HARD_PATTERNS",
    "_normalize_title_fingerprint",
    "_contains_any_title_marker",
    "_normalize_marker_word",
    "_publisher_reference_tokens",
    "_truncate_prompt_text",
]
