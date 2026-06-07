from __future__ import annotations

import ast
import importlib
from pathlib import Path


PACKAGE = Path("src/services/_publisher_inventory_service/_fetch")
FACADE = Path("src/services/_publisher_inventory_service/fetch_service.py")
FACADE_MODULE = "src.services._publisher_inventory_service.fetch_service"
MODULE_SYMBOLS = {
    "parsing.py": {
        "HTTP_BROWSER_HEADERS",
        "_InventoryHtmlParser",
        "_LandingPageInspectionHtmlParser",
    },
    "discovery.py": {
        "_discover_inventory_via_wordpress_ajax",
        "_discover_wordpress_ajax_actions",
        "discover_inventory_via_http",
    },
    "classification.py": {
        "_classify_source_surface",
        "_classify_verification",
        "_contains_price_signal",
    },
    "inspection.py": {
        "_inspect_landing_page_item",
        "inspect_inventory_landing_pages",
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


def test_publisher_fetch_uses_focused_private_owner_modules() -> None:
    facade_symbols = _owned_symbols(FACADE)
    for relative_path, expected in MODULE_SYMBOLS.items():
        owned = _owned_symbols(PACKAGE / relative_path)
        assert expected <= owned
        assert not expected & facade_symbols


def test_publisher_fetch_preserves_compatibility_surface() -> None:
    facade = importlib.import_module(FACADE_MODULE)
    for symbol in set().union(*MODULE_SYMBOLS.values()):
        assert hasattr(facade, symbol)


def test_publisher_fetch_facade_imports_owners_in_dependency_order() -> None:
    tree = ast.parse(FACADE.read_text(encoding="utf-8"), filename=str(FACADE))
    owners = [
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and "_fetch" in node.module
    ]
    assert owners == [
        "_fetch.parsing",
        "_fetch.discovery",
        "_fetch.classification",
        "_fetch.inspection",
    ]
