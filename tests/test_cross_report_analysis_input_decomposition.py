from __future__ import annotations

import ast
import importlib
from pathlib import Path


FACADE = Path("src/generators/cross_report_analysis_input_generator.py")
PACKAGE = Path("src/generators/_cross_report_analysis_input")

SHARED_SYMBOLS = {
    "_DEFAULT_THEME_SCORE_WEIGHTS",
    "_DEFAULT_SIGNAL_SCORE_WEIGHTS",
    "_RAW_METRIC_POLICY",
    "_clean_values",
    "_topic_terms",
    "_slug",
    "_taxonomy_sort_key",
    "_normalize_iso_date_filter",
    "_parse_iso_date",
    "_candidate_date",
    "_selected_source_date",
    "_source_recency_scores",
}

SOURCE_SYMBOLS = {
    "_cleaned_filters",
    "_filter_rejection_reasons",
    "_projection_readiness_rejection_reasons",
    "_relevance_score",
    "_recency_scores",
    "_score_candidates",
    "_select_diverse_sources",
    "_count_rejection_reasons",
    "select_cross_report_source_reports",
}

THEME_SYMBOLS = {
    "_theme_score_weights",
    "_weighted_theme_total",
    "_display_value",
    "_theme_candidate_from_sources",
    "_automatic_theme_candidates",
    "_theme_sort_priority",
    "_theme_novelty",
    "_load_recent_theme_metadata",
    "_explicit_theme_candidate",
    "_selected_theme",
    "select_cross_report_theme",
    "_publishability_issues",
    "validate_cross_report_publishability",
}

EVIDENCE_SYMBOLS = {
    "_ordered_selected_report_ids",
    "_evidence_sort_key",
    "_raw_metric_sort_key",
    "_prompt_input_chars",
    "_signal_score_weights",
    "_signal_label",
    "_signal_candidates",
    "_source_taxonomy_tokens",
    "_evidence_matches_signal",
    "_contradiction_score",
    "_support_score",
    "_weighted_signal_total",
    "score_cross_report_signals",
    "_directional_markers",
    "_agreement_type_and_reasons",
    "group_cross_report_evidence_agreement",
    "assemble_cross_report_analysis_inputs",
}

PUBLIC_ENTRYPOINTS = {
    "select_cross_report_source_reports",
    "select_cross_report_theme",
    "validate_cross_report_publishability",
    "assemble_cross_report_analysis_inputs",
    "score_cross_report_signals",
    "group_cross_report_evidence_agreement",
}

ALL_MOVED_SYMBOLS = SHARED_SYMBOLS | SOURCE_SYMBOLS | THEME_SYMBOLS | EVIDENCE_SYMBOLS


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


def _imported_input_siblings(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        if node.level == 1 and module in {
            "shared",
            "source_selection",
            "theme_selection",
            "evidence_signals",
        }:
            imports.add(module)
        prefix = "src.generators._cross_report_analysis_input."
        if module.startswith(prefix):
            imports.add(module.removeprefix(prefix).split(".", 1)[0])
    return imports


def test_cross_report_analysis_input_uses_semantic_private_modules() -> None:
    shared = PACKAGE / "shared.py"
    source = PACKAGE / "source_selection.py"
    theme = PACKAGE / "theme_selection.py"
    evidence = PACKAGE / "evidence_signals.py"

    assert PACKAGE.joinpath("__init__.py").is_file()
    assert shared.is_file()
    assert source.is_file()
    assert theme.is_file()
    assert evidence.is_file()

    facade_owned = _owned_symbols(FACADE)
    assert facade_owned.isdisjoint(ALL_MOVED_SYMBOLS)

    assert SHARED_SYMBOLS <= _owned_symbols(shared)
    assert SOURCE_SYMBOLS <= _owned_symbols(source)
    assert THEME_SYMBOLS <= _owned_symbols(theme)
    assert EVIDENCE_SYMBOLS <= _owned_symbols(evidence)

    assert _imported_input_siblings(shared) == set()
    assert _imported_input_siblings(source) <= {"shared"}
    assert _imported_input_siblings(theme) <= {"shared"}
    assert _imported_input_siblings(evidence) <= {"shared"}


def test_cross_report_analysis_input_facade_preserves_compatibility_imports() -> None:
    facade = importlib.import_module(
        "src.generators.cross_report_analysis_input_generator"
    )

    for symbol in ALL_MOVED_SYMBOLS | PUBLIC_ENTRYPOINTS:
        assert hasattr(facade, symbol), symbol

    namespace: dict[str, object] = {}
    exec(
        "from src.generators.cross_report_analysis_input_generator import *", namespace
    )
    for symbol in PUBLIC_ENTRYPOINTS:
        assert symbol in namespace
