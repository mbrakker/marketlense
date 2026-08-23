"""Deterministic HTML and URL evidence extraction for HTTP download routes."""

from __future__ import annotations

import re
from html.parser import HTMLParser
from urllib.parse import parse_qs, unquote, urljoin, urlsplit

_PDF_URL_PATTERN = re.compile(
    r"""(?P<quote>['"])(?P<url>[^'"]+?\.pdf(?:\?[^'"]*)?)(?P=quote)""",
    re.IGNORECASE,
)
_PDF_QUERY_KEYS = (
    "download",
    "downloadurl",
    "downloaddata",
    "file",
    "fileurl",
    "asset",
    "asseturl",
    "pdf",
    "pdfurl",
    "url",
    "target",
    "redirect",
    "redirect_url",
    "redirect_uri",
    "u",
)


class _FormRedirectParser(HTMLParser):
    def __init__(self) -> None:
        super().__init__(convert_charrefs=True)
        self.redirects: list[str] = []

    def handle_starttag(
        self, tag: str, attrs: list[tuple[str, str | None]]
    ) -> None:
        if tag.casefold() != "form":
            return
        for name, value in attrs:
            if name.casefold() == "data-redirect" and value:
                self.redirects.append(value)


def _response_header_value(headers: object, key: str) -> str:
    expected = str(key or "").casefold()
    if not hasattr(headers, "items"):
        return ""
    for header_key, value in headers.items():
        if str(header_key or "").casefold() == expected:
            return str(value or "")
    return ""


def _extract_html_title(html: str) -> str:
    match = re.search(r"(?is)<title[^>]*>(.*?)</title>", str(html or ""))
    if not match:
        return ""
    return " ".join(str(match.group(1) or "").split()).strip()


def _html_to_text(html: str) -> str:
    token = re.sub(r"(?is)<script[^>]*>.*?</script\b[^>]*>", " ", str(html or ""))
    token = re.sub(r"(?is)<style[^>]*>.*?</style\b[^>]*>", " ", token)
    token = re.sub(r"(?is)<[^>]+>", " ", token)
    token = re.sub(r"\s+", " ", token)
    return token.strip()


def _extract_text_excerpt(html: str, *, limit: int = 280) -> str:
    plain_text = _html_to_text(html)
    if len(plain_text) <= limit:
        return plain_text
    return plain_text[:limit].rstrip() + "..."


def _extract_embedded_pdf_url(*, wrapper_html: str, document_url: str) -> str | None:
    for candidate in extract_embedded_pdf_urls(
        wrapper_html=wrapper_html,
        document_url=document_url,
    ):
        return candidate
    return None


def extract_public_form_redirect_url(
    *, wrapper_html: str, document_url: str
) -> str | None:
    """Return a public HTTP target declared by a report form, when present."""
    parser = _FormRedirectParser()
    try:
        parser.feed(str(wrapper_html or ""))
        parser.close()
    except (TypeError, ValueError):
        return None
    for redirect in parser.redirects:
        candidate = urljoin(document_url, str(redirect).strip())
        parsed = urlsplit(candidate)
        if parsed.scheme in {"http", "https"} and parsed.netloc:
            return candidate
    return None


def extract_embedded_pdf_urls(*, wrapper_html: str, document_url: str) -> list[str]:
    candidates: list[str] = []
    seen: set[str] = set()
    for payload in (
        str(wrapper_html or ""),
        unquote(str(wrapper_html or "")),
        document_url,
        unquote(str(document_url or "")),
    ):
        for match in _PDF_URL_PATTERN.finditer(payload):
            raw_url = str(match.group("url") or "").strip()
            if not raw_url:
                continue
            _append_pdf_candidate(
                candidates,
                seen,
                candidate=urljoin(document_url, raw_url),
            )
        parsed = urlsplit(payload)
        if not parsed.query:
            continue
        query = parse_qs(parsed.query, keep_blank_values=False)
        for key in _PDF_QUERY_KEYS:
            values = query.get(key)
            if not values:
                continue
            for value in values:
                token = unquote(str(value or "").strip())
                if not token:
                    continue
                if token.startswith("http://") or token.startswith("https://"):
                    _append_pdf_candidate(candidates, seen, candidate=token)
                elif ".pdf" in token.casefold():
                    _append_pdf_candidate(
                        candidates,
                        seen,
                        candidate=urljoin(document_url, token),
                    )
    return candidates


def _append_pdf_candidate(
    candidates: list[str],
    seen: set[str],
    *,
    candidate: str,
) -> None:
    token = str(candidate or "").strip()
    if not token:
        return
    marker = token.casefold()
    if ".pdf" not in marker:
        return
    if marker in seen:
        return
    seen.add(marker)
    candidates.append(token)
