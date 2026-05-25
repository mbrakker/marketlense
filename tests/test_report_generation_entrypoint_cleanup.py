from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
DEPRECATED_REPORT_GENERATOR = ROOT / "src" / "generators" / "report_generator.py"
REPORT_ANALYSIS_GENERATOR = ROOT / "src" / "generators" / "report_analysis_generator.py"
DEPRECATED_ANALYSIS_FUNCTIONS = {
    "ensure_vector_store",
    "complete_report_analysis",
}


def test_deprecated_report_generation_stub_module_is_removed() -> None:
    assert not DEPRECATED_REPORT_GENERATOR.exists()


def test_report_analysis_generator_does_not_export_deprecated_entrypoint_stubs() -> (
    None
):
    tree = ast.parse(REPORT_ANALYSIS_GENERATOR.read_text(encoding="utf-8"))
    function_names = {
        node.name for node in tree.body if isinstance(node, ast.FunctionDef)
    }

    assert function_names.isdisjoint(DEPRECATED_ANALYSIS_FUNCTIONS)
