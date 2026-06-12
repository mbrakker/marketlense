from __future__ import annotations

import re

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
