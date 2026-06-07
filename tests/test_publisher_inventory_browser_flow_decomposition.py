from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "services" / "_publisher_inventory_service" / "_browser_flow"
FACADE = PACKAGE.parent / "browser_flow.py"

INTERACTION_SYMBOLS = {
    "_extract_rendered_inventory_state",
    "_dismiss_cookie_banner",
    "_reset_empty_results_filters",
    "_click_tab",
    "_click_load_more",
    "_click_pagination_next",
    "_click_archive_expander",
    "_apply_report_filter",
    "_wait_for_tab_activation",
    "_wait_for_inventory_growth",
    "_wait_for_inventory_growth_probe",
    "_wait_for_inventory_transition",
    "_prime_browser_inventory_surface",
    "_record_browser_scroll_probe_metrics",
    "_browser_wait_for_settle",
}

COLLECTION_SYMBOLS = {
    "_page_target_id",
    "_is_browser_placeholder_page_url",
    "_close_unexpected_blank_pages",
    "_extract_rendered_html_supplement_candidates",
    "_collect_browser_inventory_pages",
}

SUPPLEMENT_SYMBOLS = {
    "_HTTP_SUPPLEMENT_HTML_MAX_BYTES",
    "_extract_browser_http_supplement_candidates",
}

TRAVERSAL_SYMBOLS = {
    "_seed_initial_browser_page",
    "_run_browser_traversal",
    "_run_browser_traversal_with_timeout",
}


def _owned_symbols(path: Path) -> set[str]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    symbols: set[str] = set()
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            symbols.add(node.target.id)
    return symbols


def test_browser_flow_owner_modules_exist() -> None:
    assert (PACKAGE / "interactions.py").is_file()
    assert (PACKAGE / "collection.py").is_file()
    assert (PACKAGE / "supplement.py").is_file()
    assert (PACKAGE / "traversal.py").is_file()


def test_browser_flow_symbols_have_one_semantic_owner() -> None:
    expected = {
        "interactions.py": INTERACTION_SYMBOLS,
        "collection.py": COLLECTION_SYMBOLS,
        "supplement.py": SUPPLEMENT_SYMBOLS,
        "traversal.py": TRAVERSAL_SYMBOLS,
    }
    all_expected = set().union(*expected.values())

    for filename, symbols in expected.items():
        owned = _owned_symbols(PACKAGE / filename)
        assert owned & all_expected == symbols


def test_browser_flow_facade_imports_owners_in_dependency_order() -> None:
    module = ast.parse(FACADE.read_text(encoding="utf-8"))
    owner_imports = [
        node.module.rsplit(".", 1)[-1]
        for node in module.body
        if isinstance(node, ast.ImportFrom)
        and node.module
        and "._browser_flow." in node.module
    ]

    assert owner_imports == [
        "interactions",
        "collection",
        "supplement",
        "traversal",
    ]
