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
    "resources",
}
_LEGAL_URL_MARKERS = (
    "/legal/",
    "/laws-and-regulations/",
    "/privacy",
    "/practice-areas/",
    "/terms",
    "/cookie",
    "/compliance",
    "/gdpr",
)
_SELF_SERVICE_URL_MARKERS = (
    "/help/",
    "/registration/",
    "/sign-in",
    "/signin",
    "/sign-up",
    "/signup",
    "/get-started",
)
_CONSUMER_SELF_SERVICE_URL_MARKERS = (
    "/consumer-products/",
    "/credit/",
)
_CONSUMER_SELF_SERVICE_TITLE_MARKERS = (
    "3 bureau credit report",
    "3-bureau credit report",
    "credit monitoring",
    "credit report and fico",
    "credit report and score",
    "credit reports and scores",
    "credit score",
    "credit scores",
    "fico score",
    "fico scores",
    "free credit report",
)
_LEGAL_TITLE_MARKERS = (
    "privacy policy",
    "cookie policy",
    "terms of service",
    "terms and conditions",
    "acceptable use policy",
    "binding corporate rules",
    "bcr summary",
)
_REGULATORY_TITLE_MARKERS = (
    "pillar 3",
    "disclosure",
    "disclosures",
    "proxy statement",
    "prospectus",
    "financial statements",
)
_CORPORATE_POLICY_TITLE_MARKERS = (
    "modern slavery statement",
    "slavery statement",
    "tax strategy",
    "gender pay gap report",
    "gender pay report",
    "gender equality index",
    "equality index",
    "index de l egalite",
    "index de l égalité",
    "egalite femmes hommes",
    "égalité femmes-hommes",
    "supplier code of conduct",
    "supplier code",
    "accessibility statement",
    "whistleblowing policy",
)
_SURVEY_PLATFORM_HOST_MARKERS = (
    "surveymonkey.com",
    "qualtrics.com",
    "surveygizmo.com",
    "alchemer.com",
    "typeform.com",
    "jotform.com",
)
_CASE_STUDY_URL_MARKERS = (
    "-case-study",
    "-customer-story",
    "-success-story",
    "/case-study",
    "/case-studies/",
    "/case-studies",
    "/customer-story",
    "/customer-stories/",
    "/customer-stories",
    "/success-story",
    "/success-stories/",
)
_CASE_STUDY_TITLE_MARKERS = (
    "case study",
    "customer story",
    "success story",
)
_ANNOUNCEMENT_TITLE_MARKERS = (
    "according to new research",
    "finds new research",
    "launches new research",
    "new research from",
    "research finds",
    "study finds",
)
_SECTION_TITLE_MARKERS = {
    "about the report",
    "conclusion",
    "contents",
    "executive summary",
    "foreword",
    "introduction",
    "methodology",
    "table of contents",
}
_SECTION_URL_SLUG_MARKERS = (
    "about",
    "conclusion",
    "contents",
    "executive-summary",
    "foreword",
    "innovation",
    "introduction",
    "methodology",
    "path-to-market",
    "strategic-implications",
    "table-of-contents",
)
_INFORMATIONAL_ARTICLE_PREFIXES = (
    "how long ",
    "how to ",
    "what is ",
    "what to ",
    "why ",
    "how can ",
    "how do ",
    "how does ",
    "what can ",
)
_EDITORIAL_SECTION_URL_MARKERS = (
    "/behind-the-scenes/",
    "/company-insights/",
    "/market-insights/",
    "/market-outlook/",
    "/markets-explained/",
)
_AUDIO_EDITORIAL_URL_MARKERS = (
    "/podcast/",
    "/podcasts/",
    "/podcasts-",
    "/webcast/",
)
_AUDIO_EDITORIAL_TITLE_MARKERS = (
    "podcast",
    "roundtable",
    "webcast",
)
_BOT_CHALLENGE_MARKERS = (
    "access denied",
    "attention required",
    "captcha",
    "checking your browser",
    "just a moment",
    "security checkpoint",
    "verify you are human",
)
_TRANSIENT_FETCH_ERROR_MARKERS = (
    "connection aborted",
    "connection reset",
    "read timed out",
    "remote end closed connection",
    "temporarily unavailable",
    "timed out",
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
_SPECIFIC_REPORT_STYLE_TITLE_MARKERS = (
    "annual report",
    "barometer",
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
    "snapshot",
    "study",
    "studies",
    "survey",
    "surveys",
    "trend",
    "trends",
    "fact sheet",
    "fact sheets",
    "atlas",
    "transparency report",
    "whitepaper",
    "white paper",
)
_EDITORIAL_STRONG_REPORT_TITLE_MARKERS = (
    "annual report",
    "barometer",
    "benchmark",
    "benchmarks",
    "buyers guide",
    "buyer's guide",
    "ebook",
    "ebooks",
    "fact sheet",
    "fact sheets",
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
    "snapshot",
    "study",
    "studies",
    "survey",
    "surveys",
    "transparency report",
    "white paper",
    "whitepaper",
)
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
_REPORT_URL_PATH_MARKERS = (
    "/barometer",
    "/buyers-guide",
    "/buyers-guides/",
    "/data-report",
    "/data-reports/",
    "/fact-sheet",
    "/fact-sheets/",
    "/guide",
    "/guides/",
    "/industry-report",
    "/industry-reports/",
    "/lp/product-fact-sheet/",
    "/lp/report/",
    "/report/",
    "/reports/",
    "/report_pages/",
    "/report-hub/",
    "/special-reports/",
    "/whitepaper",
    "/whitepapers/",
    "/white-paper",
    "/ebook",
    "/ebooks/",
    "/forecast",
    "/forecasts/",
    "/study",
    "/studies/",
    "/survey",
    "/surveys/",
    "/trend",
    "/trends/",
    "/research/",
)
_REPORT_COLLECTION_URL_SEGMENTS = {
    "benchmark",
    "benchmarks",
    "ebook",
    "ebooks",
    "fact-sheet",
    "fact-sheets",
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
_SERVICE_OR_MEMBERSHIP_LEAF_MARKERS = {
    "access",
    "council",
    "membership",
    "planned",
    "reprints",
    "subscription",
    "system",
}
_SERVICE_OR_MEMBERSHIP_PATH_MARKERS = (
    "/become-a-client",
    "/capabilities/",
    "/career",
    "/careers/",
    "/events/",
    "/research-center",
    "/research-centers/",
    "/service/",
    "/services/",
    "/software/",
    "/who-we-help/",
)
_SERVICE_OR_MEMBERSHIP_TITLE_MARKERS = (
    "analyst relations council",
    "membership",
    "planned research",
    "quarterly trends hub",
    "request a call back",
    "reprints",
    "research center",
    "resource center",
    "subscription",
    "thought leadership",
)
_HARD_NON_ASSET_PATH_MARKERS = (
    "/become-a-client",
    "/capabilities/",
    "/career",
    "/careers/",
    "/events/",
    "/research-center",
    "/research-centers/",
    "/service/",
    "/services/",
    "/software/",
    "/who-we-help/",
)
_METHODOLOGY_TITLE_MARKERS = (
    "methodology",
    "methodologies",
)
_NEWS_ANALYSIS_TITLE_MARKERS = (
    " acquisition",
    " acquires ",
    " reveals about ",
    " what this ",
    " what it means ",
)
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
_TRANSIENT_HTTP_STATUS_CODES = {408, 425, 429, 500, 502, 503, 504}
_PROTECTED_DOCUMENT_HTTP_STATUS_CODES = {401, 403}
_DOCUMENT_URL_SUFFIXES = (".pdf", ".doc", ".docx", ".ppt", ".pptx", ".xls", ".xlsx")
_DATED_EDITORIAL_URL_RE = re.compile(r"/20\d{2}/\d{1,2}/\d{1,2}/")
_LEAD_CAPTURE_PATH_RE = re.compile(r"^/l/\d+/")


def _looks_like_dated_editorial_url(url: str) -> bool:
    return bool(_DATED_EDITORIAL_URL_RE.search(str(url or "").strip().casefold()))


def _looks_like_editorial_section_url(url: str) -> bool:
    lowered = str(url or "").strip().casefold()
    return any(marker in lowered for marker in _EDITORIAL_SECTION_URL_MARKERS)


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


def _looks_like_informational_article_title(lowered_title: str) -> bool:
    title = str(lowered_title or "").strip().casefold()
    if not title:
        return False
    if not title.startswith(_INFORMATIONAL_ARTICLE_PREFIXES):
        return False
    return not _contains_report_style_title_marker(title)


def _looks_like_article_label_title(lowered_title: str) -> bool:
    title = str(lowered_title or "").strip().casefold()
    if not title:
        return False
    return title.startswith("article ")


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


def _looks_like_bot_challenge_page(
    observation: PublisherInventoryLandingPageObservation,
) -> bool:
    return any(
        _looks_like_bot_challenge_text(value)
        for value in (
            observation.final_title,
            observation.h1_title,
            observation.og_title,
            observation.fetch_error,
            observation.final_url,
        )
    )


def _looks_like_bot_challenge_text(value: str) -> bool:
    normalized_value = str(value or "").strip().casefold()
    if not normalized_value:
        return False
    return any(marker in normalized_value for marker in _BOT_CHALLENGE_MARKERS)


def _looks_like_transient_fetch_failure(value: str) -> bool:
    normalized_value = str(value or "").strip().casefold()
    if not normalized_value:
        return False
    return any(marker in normalized_value for marker in _TRANSIENT_FETCH_ERROR_MARKERS)


def _looks_like_transient_http_status(status_code: int | None) -> bool:
    return int(status_code or 0) in _TRANSIENT_HTTP_STATUS_CODES


def _looks_like_protected_document_status(status_code: int | None) -> bool:
    return int(status_code or 0) in _PROTECTED_DOCUMENT_HTTP_STATUS_CODES


def _looks_like_document_url(url: str) -> bool:
    normalized_url = str(url or "").strip().casefold()
    if not normalized_url:
        return False
    return any(normalized_url.endswith(suffix) for suffix in _DOCUMENT_URL_SUFFIXES)


def _has_report_style_url_slug(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    if not path:
        return False
    slug = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("-", " ")
    return _contains_report_style_title_marker(slug)


def _has_strong_report_style_url_slug(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    if not path:
        return False
    slug = path.rsplit("/", 1)[-1].rsplit(".", 1)[0].replace("-", " ")
    return _contains_strong_editorial_report_title_marker(slug)


def _contains_specific_report_style_title_marker(title: str) -> bool:
    normalized_title = str(title or "").strip().casefold()
    if not normalized_title:
        return False
    return any(
        str(marker or "").strip().casefold() in normalized_title
        for marker in _SPECIFIC_REPORT_STYLE_TITLE_MARKERS
    )


def _contains_contextual_report_title_marker(title: str) -> bool:
    normalized_title = str(title or "").strip().casefold()
    if not normalized_title:
        return False
    tokens = [token for token in re.findall(r"[a-z0-9]+", normalized_title) if token]
    if "report" not in tokens and "reports" not in tokens:
        return False
    contextual_tokens = [
        token
        for token in tokens
        if token not in _REPORT_CONTEXT_STOP_WORDS
        and token not in {"report", "reports"}
    ]
    return len(contextual_tokens) >= 2


def _normalize_title_word(token: str) -> str:
    normalized_token = str(token or "").strip().casefold()
    if len(normalized_token) <= 4:
        return normalized_token
    if normalized_token.endswith("ies"):
        return normalized_token[:-3] + "y"
    if normalized_token.endswith("s") and not normalized_token.endswith("ss"):
        return normalized_token[:-1]
    return normalized_token


def _looks_like_self_service_page_url(url: str) -> bool:
    normalized = str(url or "").strip().casefold()
    if not normalized:
        return False
    return any(marker in normalized for marker in _SELF_SERVICE_URL_MARKERS)


def _looks_like_consumer_self_service_report_product(
    *,
    final_url_lower: str,
    resolved_title_lower: str,
    observation: PublisherInventoryLandingPageObservation,
) -> bool:
    normalized_url = str(final_url_lower or "").strip().casefold()
    normalized_title = str(resolved_title_lower or "").strip().casefold()
    if not normalized_url:
        return False
    if not any(
        marker in normalized_url for marker in _CONSUMER_SELF_SERVICE_URL_MARKERS
    ):
        return False
    if observation.is_pdf or observation.has_document_structure:
        return False
    if not (
        observation.has_gated_form
        or observation.has_download_language
        or observation.has_price_or_purchase
    ):
        return False
    return any(
        marker in normalized_title for marker in _CONSUMER_SELF_SERVICE_TITLE_MARKERS
    )


def _looks_like_report_section_url(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    segments = [segment for segment in path.split("/") if segment]
    if len(segments) < 2:
        return False
    parent_slug = segments[-2].replace("-", " ")
    child_slug = segments[-1].rsplit(".", 1)[0]
    if child_slug not in _SECTION_URL_SLUG_MARKERS:
        return False
    return _contains_report_style_title_marker(parent_slug)


def _has_report_style_url_path(final_url_lower: str) -> bool:
    normalized = str(final_url_lower or "").strip().casefold()
    if not normalized:
        return False
    return any(marker in normalized for marker in _REPORT_URL_PATH_MARKERS)


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


def _looks_like_report_collection_bucket_url(url: str) -> bool:
    path = urlsplit(str(url or "").strip().casefold()).path
    if not path:
        return False
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    return leaf in _REPORT_COLLECTION_URL_SEGMENTS


def _looks_like_audio_editorial_page(
    *,
    final_url_lower: str,
    resolved_title_lower: str,
    source_title_lower: str,
) -> bool:
    normalized_url = str(final_url_lower or "").strip().casefold()
    normalized_title = str(resolved_title_lower or "").strip().casefold()
    normalized_source_title = str(source_title_lower or "").strip().casefold()
    if any(marker in normalized_url for marker in _AUDIO_EDITORIAL_URL_MARKERS):
        return True
    combined_title = " ".join(
        part for part in (normalized_title, normalized_source_title) if part
    )
    return any(marker in combined_title for marker in _AUDIO_EDITORIAL_TITLE_MARKERS)


def _looks_like_service_or_membership_page(
    *,
    final_url_lower: str,
    resolved_title_lower: str,
) -> bool:
    normalized_url = str(final_url_lower or "").strip().casefold()
    if not normalized_url:
        return False
    path = urlsplit(normalized_url).path
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    if any(marker in normalized_url for marker in _SERVICE_OR_MEMBERSHIP_PATH_MARKERS):
        return True
    if _LEAD_CAPTURE_PATH_RE.match(path):
        return True
    leaf = segments[-1].rsplit(".", 1)[0]
    if leaf in _SERVICE_OR_MEMBERSHIP_LEAF_MARKERS:
        return True
    if any(
        leaf.endswith(f"-{marker}") or leaf.startswith(f"{marker}-")
        for marker in _SERVICE_OR_MEMBERSHIP_LEAF_MARKERS
    ):
        return True
    if leaf.endswith("-system"):
        return True
    return any(
        marker in str(resolved_title_lower or "").strip().casefold()
        for marker in _SERVICE_OR_MEMBERSHIP_TITLE_MARKERS
    )


def _looks_like_news_analysis_title(lowered_title: str) -> bool:
    normalized_title = str(lowered_title or "").strip().casefold()
    if not normalized_title:
        return False
    return any(marker in normalized_title for marker in _NEWS_ANALYSIS_TITLE_MARKERS)


def _contains_strong_editorial_report_title_marker(lowered_title: str) -> bool:
    normalized_title = str(lowered_title or "").strip().casefold()
    if not normalized_title:
        return False
    return any(
        marker in normalized_title for marker in _EDITORIAL_STRONG_REPORT_TITLE_MARKERS
    ) or _contains_contextual_report_title_marker(normalized_title)


def _looks_like_hard_non_asset_route(url: str) -> bool:
    normalized_url = str(url or "").strip().casefold()
    if not normalized_url:
        return False
    path = urlsplit(normalized_url).path
    if any(marker in normalized_url for marker in _HARD_NON_ASSET_PATH_MARKERS):
        return True
    return bool(_LEAD_CAPTURE_PATH_RE.match(path))


def _looks_like_research_hub_page(
    *,
    final_url_lower: str,
    resolved_title_lower: str,
) -> bool:
    normalized_url = str(final_url_lower or "").strip().casefold()
    normalized_title = str(resolved_title_lower or "").strip().casefold()
    if not normalized_url:
        return False
    path = urlsplit(normalized_url).path
    segments = [segment for segment in path.split("/") if segment]
    if not segments:
        return False
    leaf = segments[-1].rsplit(".", 1)[0]
    if leaf.endswith("-research-center") or leaf.endswith("-research"):
        return normalized_title.endswith(
            "research center"
        ) or normalized_title.endswith("research")
    return normalized_title.endswith("research center") or normalized_title.endswith(
        "research"
    )


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


def _looks_like_strict_collection_root_url(url: str) -> bool:
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
    return any(
        token in {"hub", "library", "center", "centre"} for token in words
    ) and all(token in _REPORT_COLLECTION_ROOT_WORDS for token in words)


def _looks_like_newsletter_source_url(source_page_url: str) -> bool:
    normalized = str(source_page_url or "").strip().casefold()
    if not normalized:
        return False
    return "newsletter" in normalized or "/newsletters/" in normalized


def _looks_like_report_section_title(title: str) -> bool:
    normalized_title = str(title or "").strip().casefold()
    if not normalized_title:
        return False
    if normalized_title in _SECTION_TITLE_MARKERS:
        return True
    return bool(re.fullmatch(r"(chapter|part|section)\s+\d+[a-z]?", normalized_title))


def _looks_like_survey_platform_page(url: str) -> bool:
    normalized = str(url or "").strip().casefold()
    if not normalized:
        return False
    return any(marker in normalized for marker in _SURVEY_PLATFORM_HOST_MARKERS)
