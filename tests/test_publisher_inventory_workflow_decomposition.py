from __future__ import annotations

import ast
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "services" / "_publisher_inventory_service"

PREFLIGHT_SYMBOLS = {
    "_PREFLIGHT_HTML_MAX_BYTES",
    "_DIRECT_DETAIL_URL_MARKERS",
    "_ARCHIVE_URL_MARKERS",
    "_FILTER_HINT_MARKERS",
    "_DOWNLOAD_HINT_MARKERS",
    "_PREFLIGHT_COLLECTION_ROOT_TOKENS",
    "_build_scenario_summary",
    "_classify_preflight_scenario",
    "_looks_like_preflight_filter_route",
    "_looks_like_preflight_direct_detail_path",
}

BROWSER_FLOW_SYMBOLS = {
    "_HTTP_SUPPLEMENT_HTML_MAX_BYTES",
    "_seed_initial_browser_page",
    "_run_browser_traversal",
    "_run_browser_traversal_with_timeout",
    "_page_target_id",
    "_is_browser_placeholder_page_url",
    "_close_unexpected_blank_pages",
    "_extract_rendered_html_supplement_candidates",
    "_collect_browser_inventory_pages",
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
    "_extract_browser_http_supplement_candidates",
}

WORKFLOW_COORDINATOR_SYMBOLS = {
    "_ROUTE_KINDS",
    "discover_publisher_inventory",
    "inspect_publisher_inventory_landing_pages",
    "_discover_direct_pdf_source",
    "_discover_direct_detail_source",
    "_discover_with_http",
    "_discover_with_browser",
    "_candidate_provenance_counts",
    "_validate_request",
    "_validate_route_kind",
    "_validate_and_normalize_url",
    "_prepare_session_dir",
    "_load_browser_use_runtime",
    "_kill_browser",
}

ALL_OWNED_SYMBOLS = (
    PREFLIGHT_SYMBOLS | BROWSER_FLOW_SYMBOLS | WORKFLOW_COORDINATOR_SYMBOLS
)


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


def test_publisher_inventory_workflow_owner_modules_exist() -> None:
    assert (PACKAGE / "preflight.py").is_file()
    assert (PACKAGE / "browser_flow.py").is_file()
    assert (PACKAGE / "_browser_flow").is_dir()


def test_publisher_inventory_workflow_symbols_have_semantic_owners() -> None:
    workflow_symbols = _owned_symbols(PACKAGE / "workflow.py")
    preflight_symbols = _owned_symbols(PACKAGE / "preflight.py")
    browser_flow_symbols = set().union(
        *(_owned_symbols(path) for path in (PACKAGE / "_browser_flow").glob("*.py"))
    )

    assert PREFLIGHT_SYMBOLS <= preflight_symbols
    assert BROWSER_FLOW_SYMBOLS <= browser_flow_symbols
    assert WORKFLOW_COORDINATOR_SYMBOLS <= workflow_symbols

    assert not (PREFLIGHT_SYMBOLS & workflow_symbols)
    assert not (BROWSER_FLOW_SYMBOLS & workflow_symbols)
    assert preflight_symbols & ALL_OWNED_SYMBOLS == PREFLIGHT_SYMBOLS
    assert browser_flow_symbols & ALL_OWNED_SYMBOLS == BROWSER_FLOW_SYMBOLS
    assert workflow_symbols & ALL_OWNED_SYMBOLS == WORKFLOW_COORDINATOR_SYMBOLS


def test_publisher_inventory_workflow_compatibility_exports_remain() -> None:
    facade = importlib.import_module("src.services.publisher_inventory_service")

    for symbol in ALL_OWNED_SYMBOLS:
        assert hasattr(facade, symbol), symbol
