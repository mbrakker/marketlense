from __future__ import annotations

import re
from urllib.parse import parse_qsl, urlencode, urlsplit, urlunsplit

_TRACKING_QUERY_KEYS = {
    "fbclid",
    "gclid",
    "dclid",
    "msclkid",
    "mc_cid",
    "mc_eid",
    "icid",
}
_TRACKING_QUERY_PREFIXES = (
    "utm_",
    "hsa_",
)


def normalize_url(url: str) -> str:
    token = str(url).strip()
    if not token:
        return ""
    parts = urlsplit(token)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    path = parts.path or "/"
    if path != "/" and path.endswith("/"):
        path = path.rstrip("/")
    normalized_pairs = [
        (key, value)
        for key, value in parse_qsl(parts.query, keep_blank_values=True)
        if not _should_strip_query_param(key)
    ]
    normalized_query = urlencode(normalized_pairs, doseq=True)
    return urlunsplit((scheme, netloc, path, normalized_query, ""))


def host_matches_domain(value: str, domain: str) -> bool:
    expected = _hostname_token(domain)
    host = _hostname_token(value)
    if not host or not expected:
        return False
    return host == expected or host.endswith(f".{expected}")


def text_has_url_or_domain_marker(text: str, *, domains: set[str]) -> bool:
    token = " ".join(str(text or "").split())
    if not token:
        return False
    if re.search(r"\b[a-z][a-z0-9+.-]*://", token, flags=re.IGNORECASE):
        return True
    for domain in domains:
        escaped = re.escape(_hostname_token(domain))
        if not escaped:
            continue
        if re.search(
            rf"(?<![A-Za-z0-9.-]){escaped}(?=[:/?#\s]|$)",
            token,
            flags=re.IGNORECASE,
        ):
            return True
    return False


def _should_strip_query_param(key: str) -> bool:
    normalized_key = str(key or "").strip().casefold()
    if not normalized_key:
        return False
    if normalized_key in _TRACKING_QUERY_KEYS:
        return True
    return normalized_key.startswith(_TRACKING_QUERY_PREFIXES)


def _hostname_token(value: str) -> str:
    token = str(value or "").strip().casefold()
    if not token:
        return ""
    parsed = urlsplit(token)
    if not parsed.hostname and "://" not in token:
        parsed = urlsplit(f"//{token}")
    return str(parsed.hostname or "").strip(".").casefold()
