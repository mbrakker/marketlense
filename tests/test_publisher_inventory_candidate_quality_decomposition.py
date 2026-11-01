from __future__ import annotations

import ast
import importlib
from pathlib import Path

from src.generators.publisher_inventory_candidate_quality_generator import (
    _contains_report_style_title_marker,
    _looks_like_publication_detail_url,
    _looks_like_report_collection_root_url,
    _normalize_title,
)


PACKAGE = Path("src/generators/_publisher_inventory_candidate_quality")
FACADE = Path("src/generators/publisher_inventory_candidate_quality_generator.py")
FACADE_MODULE = "src.generators.publisher_inventory_candidate_quality_generator"
MODULE_SYMBOLS = {
    "classification.py": {
        "_GENERIC_TITLE_TOKENS",
        "_contains_report_style_title_marker",
        "_looks_like_publication_detail_url",
        "_looks_like_report_collection_root_url",
        "_normalize_title",
        "_resolve_candidate_title",
    },
    "evaluation.py": {
        "_build_recovery_recipe",
        "_qualify_observation",
    },
    "workflow.py": {
        "qualify_publisher_inventory_candidates",
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


def test_candidate_quality_uses_focused_private_owner_modules() -> None:
    facade_symbols = _owned_symbols(FACADE)
    for relative_path, expected in MODULE_SYMBOLS.items():
        owned = _owned_symbols(PACKAGE / relative_path)
        assert expected <= owned
        assert not expected & facade_symbols


def test_candidate_quality_preserves_compatibility_surface() -> None:
    facade = importlib.import_module(FACADE_MODULE)
    for symbol in set().union(*MODULE_SYMBOLS.values()):
        assert hasattr(facade, symbol)


def test_candidate_quality_facade_imports_owners_in_dependency_order() -> None:
    tree = ast.parse(FACADE.read_text(encoding="utf-8"), filename=str(FACADE))
    owners = [
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and "_publisher_inventory_candidate_quality" in node.module
    ]
    assert owners == [
        "_publisher_inventory_candidate_quality.classification",
        "_publisher_inventory_candidate_quality.evaluation",
        "_publisher_inventory_candidate_quality.workflow",
    ]


def test_candidate_quality_title_compatibility_normalizes_real_landing_titles() -> None:
    assert _normalize_title("Download now 2026 Retail Report") == ("2026 Retail Report")
    assert _normalize_title("Research Pack PDF 2.5 MB") == "Research Pack"
    assert _normalize_title("Research brief...") == "Research brief"
    assert _normalize_title("Reports") == ""
    assert _contains_report_style_title_marker("2026 Retail Studies")
    assert _contains_report_style_title_marker("Customer Research White Paper")
    assert not _contains_report_style_title_marker("Customer story")


def test_candidate_quality_url_compatibility_distinguishes_detail_and_collection() -> (
    None
):
    assert _looks_like_publication_detail_url(
        "https://example.test/publications/retail_report.html"
    )
    assert _looks_like_publication_detail_url(
        "https://example.test/publications/retail_report"
    )
    assert not _looks_like_publication_detail_url("https://example.test/publications/")
    assert not _looks_like_publication_detail_url(
        "https://example.test/publications/2026"
    )

    assert _looks_like_report_collection_root_url("https://example.test/reports")
    assert _looks_like_report_collection_root_url(
        "https://example.test/research/library"
    )
    assert not _looks_like_report_collection_root_url(
        "https://example.test/reports/customer-story"
    )
