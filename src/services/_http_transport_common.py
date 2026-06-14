"""Shared HTTP pool identity without cross-service request behavior."""

from __future__ import annotations

from urllib.parse import urlsplit


def session_pool_key(url: str) -> str:
    parsed = urlsplit(str(url or "").strip())
    scheme = str(parsed.scheme or "").strip().casefold() or "https"
    host = str(parsed.netloc or "").strip().casefold()
    return f"{scheme}://{host}" if host else scheme
