from __future__ import annotations

import ast
from pathlib import Path


PACKAGE = Path("src/services/_browser_report_download")
HELPERS = PACKAGE / "helpers.py"
HELPER_PACKAGE = PACKAGE / "_helpers"

STATE_SYMBOLS = {
    "_HELPER_SCHEMA_VERSION",
    "_HTML_EXCERPT_CHARS",
    "_HELPER_AWAIT_TIMEOUT_SECONDS",
    "_INTERNAL_TARGET_URL_PREFIXES",
    "browser_helper_page_info",
    "browser_helper_wait_for_load",
    "browser_helper_ensure_real_tab",
    "_log_wait_result",
    "_find_real_tab_via_cdp",
    "_log_real_tab_result",
    "_first_non_empty",
    "_looks_like_browser_use_session",
    "_read_browser_url",
    "_read_browser_title",
    "_read_browser_html",
    "_read_browser_current_page_url",
    "_read_browser_current_page_title",
    "_read_page_url",
    "_read_page_title",
    "_read_page_html",
    "_is_real_tab_url",
    "_maybe_await",
    "_await_async",
    "_excerpt",
}

INSPECTION_SYMBOLS = {
    "_JS_SNIPPET_CHARS",
    "_JavaScriptEvaluationError",
    "browser_helper_js",
    "browser_helper_js_async",
    "browser_helper_http_get",
    "_js_failure",
    "_adapt_js_result_value",
    "_coerce_json_envelope",
    "_wrap_js_expression",
    "_looks_like_js_function",
    "_looks_like_statement_script",
    "_is_js_error_envelope",
    "_unwrap_js_success_envelope",
    "_is_json_serializable",
    "_coerce_optional_int",
    "_extract_error_location",
    "_snippet",
}

INTERACTION_SYMBOLS = {
    "_SELECTOR_HOSTILE_SURFACE_LABELS",
    "browser_helper_capture_screenshot",
    "browser_helper_coordinate_fallback_click",
    "browser_helper_form_autocomplete",
    "_autocomplete_result",
    "_screenshot_result",
    "_coordinate_fallback_result",
    "_coordinate_fallback_policy",
    "_normalize_surface_labels",
    "_has_selector_hostile_surface",
    "_coordinates_are_usable",
    "_after_coordinate_screenshot_path",
    "_try_screenshot_call",
}

FACADE_EXPORTS = {
    "get_browser_helper_surface",
    *STATE_SYMBOLS,
    *INSPECTION_SYMBOLS,
    *INTERACTION_SYMBOLS,
}


def _owned_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owned: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            owned.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    owned.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            owned.add(node.target.id)
    return owned


def _imported_helper_siblings(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom):
            module = node.module or ""
            if node.level == 1 and module in {"state", "inspection", "interaction"}:
                imports.add(module)
            if module.startswith("src.services._browser_report_download._helpers."):
                imports.add(module.rsplit(".", 1)[-1])
    return imports


def test_browser_download_helpers_use_semantic_private_modules() -> None:
    state = HELPER_PACKAGE / "state.py"
    inspection = HELPER_PACKAGE / "inspection.py"
    interaction = HELPER_PACKAGE / "interaction.py"

    assert HELPER_PACKAGE.joinpath("__init__.py").is_file()
    assert state.is_file()
    assert inspection.is_file()
    assert interaction.is_file()

    facade_owned = _owned_symbols(HELPERS)
    assert {"get_browser_helper_surface"} <= facade_owned
    assert facade_owned.isdisjoint(
        STATE_SYMBOLS | INSPECTION_SYMBOLS | INTERACTION_SYMBOLS
    )

    assert STATE_SYMBOLS <= _owned_symbols(state)
    assert INSPECTION_SYMBOLS <= _owned_symbols(inspection)
    assert INTERACTION_SYMBOLS <= _owned_symbols(interaction)

    assert _imported_helper_siblings(state) == set()
    assert _imported_helper_siblings(inspection) <= {"state"}
    assert _imported_helper_siblings(interaction) <= {"state", "inspection"}


def test_browser_download_helper_facade_preserves_compatibility_imports() -> None:
    namespace: dict[str, object] = {}
    exec(
        "from src.services._browser_report_download.helpers import *",
        namespace,
    )

    for symbol in FACADE_EXPORTS:
        assert symbol in namespace
