from __future__ import annotations

import ast
import importlib
from pathlib import Path


PACKAGE = Path("src/services/_pdf/_figures")
FACADE = Path("src/services/_pdf/figures.py")
FACADE_MODULE = "src.services._pdf.figures"
MODULE_SYMBOLS = {
    "triage.py": {
        "_CandidatePagePlan",
        "_CandidatePageScore",
        "_candidate_page_drawing_count",
        "_degraded_page_record",
        "_plan_candidate_pages",
        "_resolve_degraded_page_action",
        "_resolve_page_gate_recall_floor",
        "_score_candidate_page",
    },
    "pruning.py": {
        "_final_chart_candidate_looks_forecast_table",
        "_final_chart_header_reanchor_line",
        "_panel_title_looks_short_proper_name",
        "_prune_charts_overlapping_ranked_tables",
        "_prune_final_chart_candidates",
        "_prune_tables_overlapping_chart_panels",
    },
    "best_figure.py": {
        "_extract_best_figure_png",
        "_figure_nearest_block_text",
        "_figure_score_text",
        "extract_best_figure",
    },
    "candidates.py": {
        "_CandidateExtractionArtifacts",
        "_annotate_degraded_candidates",
        "_extract_candidate_artifacts",
        "_finalize_chart_collection",
        "collect_candidates",
    },
}
COMPATIBILITY_SYMBOLS = set().union(*MODULE_SYMBOLS.values())


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


def test_pdf_figures_uses_focused_private_capability_modules() -> None:
    facade_symbols = _owned_symbols(FACADE)

    for relative_path, expected in MODULE_SYMBOLS.items():
        owned = _owned_symbols(PACKAGE / relative_path)
        assert expected <= owned
        assert not expected & facade_symbols


def test_pdf_figures_preserves_compatibility_surface() -> None:
    facade = importlib.import_module(FACADE_MODULE)

    for symbol in COMPATIBILITY_SYMBOLS:
        assert hasattr(facade, symbol)


def test_pdf_figures_facade_imports_owners_in_dependency_order() -> None:
    tree = ast.parse(FACADE.read_text(encoding="utf-8"), filename=str(FACADE))
    owners = [
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and "_figures" in node.module
    ]
    assert owners == [
        "_figures.triage",
        "_figures.pruning",
        "_figures.candidates",
        "_figures.best_figure",
    ]
