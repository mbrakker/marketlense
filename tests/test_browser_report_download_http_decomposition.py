from __future__ import annotations

import ast
from pathlib import Path


PACKAGE = Path("src/services/_browser_report_download")
HTTP = PACKAGE / "http.py"
COMPATIBILITY_EXPORTS = {
    "DirectOnsiteRecoveryDecision",
    "download_pdf_from_url",
    "ensure_downloaded_pdf",
    "extract_embedded_pdf_urls",
    "fetch_html_from_url",
    "is_pdf_file",
    "resolve_downloaded_mime_type",
    "try_direct_onsite_capture",
    "try_direct_pdf_download",
    "try_http_access_challenge_probe",
    "try_report_page_pdf_link_download",
    "try_static_email_gate_probe",
    "validate_downloaded_pdf_artifact",
}
MODULE_FUNCTIONS = {
    "_http/pdf_transfer.py": {
        "try_direct_pdf_download",
        "ensure_downloaded_pdf",
        "resolve_downloaded_mime_type",
        "validate_downloaded_pdf_artifact",
        "is_pdf_file",
        "download_pdf_from_url",
    },
    "_http/page_pdf_probe.py": {
        "try_report_page_pdf_link_download",
    },
    "_http/gate_probe.py": {
        "try_http_access_challenge_probe",
        "try_static_email_gate_probe",
    },
    "_http/onsite_capture.py": {
        "DirectOnsiteRecoveryDecision",
        "try_direct_onsite_capture",
    },
    "_http/html_evidence.py": {
        "_extract_html_title",
        "_html_to_text",
        "_extract_text_excerpt",
        "_response_header_value",
        "extract_embedded_pdf_urls",
    },
}


def _owned_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_browser_report_http_uses_focused_private_capability_modules() -> None:
    coordinator_symbols = _owned_symbols(HTTP)
    for relative_path, expected_symbols in MODULE_FUNCTIONS.items():
        owned_symbols = _owned_symbols(PACKAGE / relative_path)
        assert expected_symbols <= owned_symbols
        assert not expected_symbols & coordinator_symbols

    source = HTTP.read_text(encoding="utf-8")
    for symbol in COMPATIBILITY_EXPORTS:
        assert symbol in source
