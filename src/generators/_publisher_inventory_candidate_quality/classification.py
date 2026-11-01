from __future__ import annotations

import re
from urllib.parse import urlsplit

from src.contracts.publisher_inventory import PublisherInventoryLandingPageObservation

_GENERIC_TITLE_TOKENS = {
    "",
    "heading 1",
    "read now",
    "download now",
    "learn more",
    "read report",
    "download report",
    "view report",
    "report",
    "reports",
    "whitepaper",
    "white paper",
    "ebook",
    "page not found",
    "key takeaways",
    "takeaways",
    "here",
    "online here",
    "white papers",
    "whitepapers",
    "research",
    "studies",
    "guides",
    "playbooks",
    "benchmarks",
    "surveys",
    "outlooks",
    "forecasts",
}
_BOT_CHALLENGE_MARKERS = (
    "access denied",
    "attention required",
    "captcha",
    "checking your browser",
    "just a moment",
    "security checkpoint",
    "verify you are human",
)
_REPORT_STYLE_TITLE_MARKERS = (
    "barometer",
    "report",
    "reports",
    "benchmark",
    "benchmarks",
    "study",
    "studies",
    "research",
    "survey",
    "surveys",
    "outlook",
    "outlooks",
    "playbook",
    "playbooks",
    "blueprint",
    "whitepaper",
    "white paper",
    "guide",
    "guides",
    "ebook",
    "ebooks",
    "fact sheet",
    "fact sheets",
    "forecast",
    "forecasts",
    "atlas",
    "buyers guide",
    "buyer's guide",
    "infographic",
    "snapshot",
    "trend",
    "trends",
)
_REPORT_COLLECTION_URL_SEGMENTS = {
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
    "study",
    "studies",
    "survey",
    "surveys",
    "trend",
    "trends",
    "whitepaper",
    "whitepapers",
    "white-paper",
}
_REPORT_COLLECTION_ROOT_WORDS = {
    "all",
    "and",
    "asset",
    "assets",
    "benchmark",
    "benchmarks",
    "center",
    "centre",
    "ebook",
    "ebooks",
    "guide",
    "guides",
    "hub",
    "index",
    "library",
    "paper",
    "papers",
    "playbook",
    "playbooks",
    "quarterly",
    "report",
    "reports",
    "research",
    "resource",
    "resources",
    "study",
    "studies",
    "survey",
    "surveys",
    "thought",
    "trend",
    "trends",
    "white",
    "whitepaper",
    "whitepapers",
}


def _resolve_candidate_title(
    source_title: str,
    observation: PublisherInventoryLandingPageObservation,
) -> str:
    fallback_title = (
        observation.final_url.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("-", " ")
    )
    for candidate_title in (
        observation.h1_title,
        observation.og_title,
        observation.final_title,
        source_title,
        fallback_title,
    ):
        if _looks_like_bot_challenge_text(candidate_title):
            continue
        normalized = _normalize_title(candidate_title)
        if normalized:
            return normalized
    return _normalize_title(fallback_title) or observation.canonical_url


def _normalize_title(value: str) -> str:
    normalized = " ".join(str(value or "").split()).strip()
    lowered = normalized.casefold()
    if not normalized or lowered in _GENERIC_TITLE_TOKENS:
        return ""
    if lowered.startswith(
        ("read now ", "learn more ", "download report ", "download now ")
    ):
        normalized = normalized.split(" ", 2)[-1].strip()
        lowered = normalized.casefold()
    normalized = re.sub(
        r"\s*(?:pdf|docx?|xlsx?|pptx?)\s*\d+(?:\.\d+)?\s*(?:kb|mb|gb)\s*$",
        "",
        normalized,
        flags=re.IGNORECASE,
    ).rstrip()
    lowered = normalized.casefold()
    normalized = normalized.rstrip(". ")
    if normalized.endswith("..."):
        normalized = normalized[:-3].rstrip()
        lowered = normalized.casefold()
    if lowered in _GENERIC_TITLE_TOKENS:
        return ""
    return normalized


def _looks_like_bot_challenge_text(value: str) -> bool:
    normalized_value = str(value or "").strip().casefold()
    if not normalized_value:
        return False
    return any(marker in normalized_value for marker in _BOT_CHALLENGE_MARKERS)


def _contains_report_style_title_marker(title: str) -> bool:
    normalized_title = str(title or "").strip().casefold()
    if not normalized_title:
        return False
    words = {
        _normalize_title_word(token)
        for token in re.findall(r"[a-z0-9]+", normalized_title)
        if token
    }
    for marker in _REPORT_STYLE_TITLE_MARKERS:
        normalized_marker = str(marker or "").strip().casefold()
        if not normalized_marker:
            continue
        if " " in normalized_marker:
            if normalized_marker in normalized_title:
                return True
            continue
        if _normalize_title_word(normalized_marker) in words:
            return True
    return False


def _normalize_title_word(token: str) -> str:
    normalized_token = str(token or "").strip().casefold()
    if len(normalized_token) <= 4:
        return normalized_token
    if normalized_token.endswith("ies"):
        return normalized_token[:-3] + "y"
    if normalized_token.endswith("s") and not normalized_token.endswith("ss"):
        return normalized_token[:-1]
    return normalized_token


def _looks_like_publication_detail_url(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    if "/publications/" not in path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    raw_leaf = segments[-1]
    leaf = raw_leaf.rsplit(".", 1)[0]
    if leaf in {"publication", "publications"} or leaf.isdigit():
        return False
    return raw_leaf.endswith(".html") or "_" in leaf


def _looks_like_report_collection_root_url(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    if leaf in _REPORT_COLLECTION_URL_SEGMENTS:
        return True
    words = [token for token in re.findall(r"[a-z0-9]+", leaf) if token]
    if not words:
        return False
    if not any(
        token in _REPORT_COLLECTION_URL_SEGMENTS
        or token
        in {"hub", "library", "center", "centre", "research", "reports", "report"}
        for token in words
    ):
        return False
    return all(token in _REPORT_COLLECTION_ROOT_WORDS for token in words)


__all__ = [
    "_GENERIC_TITLE_TOKENS",
    "_REPORT_STYLE_TITLE_MARKERS",
    "_REPORT_COLLECTION_URL_SEGMENTS",
    "_REPORT_COLLECTION_ROOT_WORDS",
    "_resolve_candidate_title",
    "_normalize_title",
    "_contains_report_style_title_marker",
    "_looks_like_publication_detail_url",
    "_looks_like_report_collection_root_url",
]
