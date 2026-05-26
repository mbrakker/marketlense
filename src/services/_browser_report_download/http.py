"""Compatibility surface for private browser-report HTTP capabilities."""

from __future__ import annotations

# Kept as a compatibility-boundary handle for tests that substitute true HTTP I/O.
import requests as requests

from src.services._browser_report_download._http.gate_probe import (
    try_http_access_challenge_probe,
    try_static_email_gate_probe,
)
from src.services._browser_report_download._http.html_evidence import (
    extract_embedded_pdf_urls,
)
from src.services._browser_report_download._http.onsite_capture import (
    DirectOnsiteRecoveryDecision,
    try_direct_onsite_capture,
)
from src.services._browser_report_download._http.page_pdf_probe import (
    try_report_page_pdf_link_download,
)
from src.services._browser_report_download._http.pdf_transfer import (
    download_pdf_from_url,
    ensure_downloaded_pdf,
    fetch_html_from_url,
    is_pdf_file,
    resolve_downloaded_mime_type,
    try_direct_pdf_download,
    validate_downloaded_pdf_artifact,
)

__all__ = [
    "DirectOnsiteRecoveryDecision",
    "download_pdf_from_url",
    "ensure_downloaded_pdf",
    "extract_embedded_pdf_urls",
    "fetch_html_from_url",
    "is_pdf_file",
    "requests",
    "resolve_downloaded_mime_type",
    "try_direct_onsite_capture",
    "try_direct_pdf_download",
    "try_http_access_challenge_probe",
    "try_report_page_pdf_link_download",
    "try_static_email_gate_probe",
    "validate_downloaded_pdf_artifact",
]
