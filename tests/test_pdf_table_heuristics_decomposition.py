from __future__ import annotations

import ast
from pathlib import Path


PACKAGE = Path("src/services/_pdf")
FACADE = PACKAGE / "table_heuristics.py"
MODULE_SYMBOLS = {
    "_table_heuristics/policy.py": {
        "TABLE_SETTINGS_LATTICE",
        "TABLE_SETTINGS_STREAM",
        "TABLE_DEDUP_IOU",
    },
    "_table_heuristics/models.py": {
        "_TableCandidate",
        "_PageTextBlock",
        "_PageTextLine",
        "_TableTextBand",
        "_RankedTableRegion",
    },
    "_table_heuristics/layout.py": {
        "_table_page_text_blocks",
        "_table_text_bands",
        "_table_preview",
        "_extract_text_in_bbox",
        "_text_stats",
    },
    "_table_heuristics/regions.py": {
        "_detect_ranked_table_candidates",
        "_compose_table_bbox",
        "_expand_table_bbox",
    },
    "_table_heuristics/screening.py": {
        "_validate_table_candidate",
        "_dedupe_table_candidates",
        "_table_quality",
    },
}
COMPATIBILITY_SYMBOLS = {
    "TABLE_SETTINGS_LATTICE",
    "TABLE_SETTINGS_STREAM",
    "_TableCandidate",
    "_table_page_text_blocks",
    "_table_text_bands",
    "_detect_ranked_table_candidates",
    "_compose_table_bbox",
    "_expand_table_bbox",
    "_table_preview",
    "_extract_text_in_bbox",
    "_text_stats",
    "_validate_table_candidate",
    "_dedupe_table_candidates",
    "_resolve_candidate_parallel_workers",
    "_suppress_pdfminer_warnings",
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


def test_pdf_table_heuristics_use_focused_private_capability_modules() -> None:
    facade_symbols = _owned_symbols(FACADE)
    for relative_path, expected in MODULE_SYMBOLS.items():
        owned = _owned_symbols(PACKAGE / relative_path)
        assert expected <= owned
        assert not expected & facade_symbols

    source = FACADE.read_text(encoding="utf-8")
    for symbol in COMPATIBILITY_SYMBOLS:
        assert symbol in source
