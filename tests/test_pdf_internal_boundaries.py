from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]


def test_pdf_candidate_capabilities_do_not_import_figures_internals() -> None:
    paths = [
        ROOT / "src/services/_pdf/visual_candidates.py",
        ROOT / "src/services/_pdf/table_candidates.py",
        *sorted((ROOT / "src/services/_pdf/_visual_candidates").glob("*.py")),
    ]
    for path in paths:
        relative_path = path.relative_to(ROOT).as_posix()
        tree = ast.parse(path.read_text(encoding="utf-8"))
        forbidden: list[int] = []
        for node in ast.walk(tree):
            if isinstance(node, ast.ImportFrom) and node.module == "figures":
                forbidden.append(node.lineno)
        assert forbidden == [], (
            f"{relative_path} must import shared heuristics from explicit internal "
            f"modules, not from figures.py: lines {forbidden}"
        )
