"""Shared immutable HTTP acquisition configuration for browser report download."""

from __future__ import annotations

_PDF_FETCH_HEADERS = {
    "Accept": "application/pdf,application/octet-stream;q=0.9,*/*;q=0.8",
    "User-Agent": (
        "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/136.0.0.0 Safari/537.36"
    ),
}
_PDF_FETCH_FALLBACK_HEADERS = {
    "Accept": _PDF_FETCH_HEADERS["Accept"],
}
_HTML_FETCH_HEADERS = {
    "Accept": "text/html,application/xhtml+xml;q=0.9,*/*;q=0.8",
    "User-Agent": _PDF_FETCH_HEADERS["User-Agent"],
}
_HTML_FETCH_MAX_BYTES = 4 * 1024 * 1024
_PDF_FETCH_MAX_BYTES = 128 * 1024 * 1024
