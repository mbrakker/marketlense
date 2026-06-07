from __future__ import annotations

import ast
import importlib
from pathlib import Path


PACKAGE = Path("src/services/_browser_report_download/_cdp")
FACADE = Path("src/services/_browser_report_download/cdp.py")
FACADE_MODULE = "src.services._browser_report_download.cdp"
MODULE_SYMBOLS = {
    "models.py": {
        "BrowserDownloadCdpCallResult",
        "BrowserDownloadTargetHygieneResult",
        "_ResolvedCdpSession",
        "_CDP_ALLOWLIST",
    },
    "transport.py": {
        "_await_cdp_client_operation",
        "_await_with_timeout",
        "_extract_runtime_value",
        "_send_raw_cdp",
    },
    "session.py": {
        "_resolve_browser_cdp_session",
        "_select_real_page_target_info",
        "_send_browser_download_cdp",
    },
    "dialogs.py": {
        "_collect_terminal_dialog_evidence_via_cdp",
        "_dialog_policy_action",
        "_sanitize_dialog_message",
    },
    "operations.py": {
        "call_browser_download_cdp",
        "capture_print_pdf_via_cdp",
        "collect_terminal_network_entries_via_cdp",
        "ensure_browser_download_target_hygiene_via_cdp",
    },
}


def _owned_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    symbols = {
        node.name
        for node in tree.body
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
    }
    for node in tree.body:
        if isinstance(node, ast.Assign):
            symbols.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            symbols.add(node.target.id)
    return symbols


def test_browser_cdp_uses_focused_private_owner_modules() -> None:
    facade_symbols = _owned_symbols(FACADE)
    for relative_path, expected in MODULE_SYMBOLS.items():
        owned = _owned_symbols(PACKAGE / relative_path)
        assert expected <= owned
        assert not expected & facade_symbols


def test_browser_cdp_preserves_compatibility_surface() -> None:
    facade = importlib.import_module(FACADE_MODULE)
    for symbol in set().union(*MODULE_SYMBOLS.values()):
        assert hasattr(facade, symbol)


def test_browser_cdp_facade_imports_owners_in_dependency_order() -> None:
    tree = ast.parse(FACADE.read_text(encoding="utf-8"), filename=str(FACADE))
    owners = [
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and "_cdp" in node.module
    ]
    assert owners == [
        "_cdp.models",
        "_cdp.transport",
        "_cdp.session",
        "_cdp.dialogs",
        "_cdp.operations",
    ]
