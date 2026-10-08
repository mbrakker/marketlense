from __future__ import annotations

import re
from urllib.parse import (
    SplitResult,
    parse_qsl,
    unquote_plus,
    urlencode,
    urlsplit,
    urlunsplit,
)

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
_SIGNED_QUERY_KEYS = {
    "awsaccesskeyid",
    "googleaccessid",
    "hdnea",
    "key-pair-id",
    "policy",
    "sig",
    "signature",
}
_SIGNED_QUERY_PREFIXES = ("x-amz-", "x-goog-")


def normalize_url(url: str) -> str:
    token = str(url).strip()
    if not token:
        return ""
    parts = urlsplit(token)
    scheme = parts.scheme.lower()
    netloc = parts.netloc.lower()
    if _has_signed_query(parts.query):
        return urlunsplit(
            (scheme, _normalized_netloc(parts), parts.path, parts.query, "")
        )
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


def url_identity(url: str) -> str:
    """Normalize only HTTP origin case and default ports for URL deduplication."""
    token = str(url or "").strip()
    if not token:
        return ""
    parts = urlsplit(token)
    scheme = parts.scheme.casefold()
    try:
        netloc = _normalized_netloc(parts)
    except ValueError:
        return token
    return urlunsplit((scheme, netloc, parts.path, parts.query, parts.fragment))


def _has_signed_query(query: str) -> bool:
    for pair in str(query or "").split("&"):
        key = unquote_plus(pair.split("=", 1)[0]).casefold()
        if key in _SIGNED_QUERY_KEYS or key.startswith(_SIGNED_QUERY_PREFIXES):
            return True
    return False


def _normalized_netloc(parts: SplitResult) -> str:
    hostname = str(parts.hostname or "").casefold()
    if not hostname:
        return parts.netloc.casefold()
    try:
        port = parts.port
    except ValueError:
        return parts.netloc.casefold()
    user_info = parts.netloc.rsplit("@", 1)[0] + "@" if "@" in parts.netloc else ""
    host = (
        f"[{hostname}]"
        if ":" in hostname and not hostname.startswith("[")
        else hostname
    )
    default_port = (parts.scheme.casefold() == "http" and port == 80) or (
        parts.scheme.casefold() == "https" and port == 443
    )
    port_suffix = f":{port}" if port is not None and not default_port else ""
    return f"{user_info}{host}{port_suffix}"


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
