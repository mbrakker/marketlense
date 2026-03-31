from __future__ import annotations

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


def _should_strip_query_param(key: str) -> bool:
    normalized_key = str(key or "").strip().casefold()
    if not normalized_key:
        return False
    if normalized_key in _TRACKING_QUERY_KEYS:
        return True
    return normalized_key.startswith(_TRACKING_QUERY_PREFIXES)
