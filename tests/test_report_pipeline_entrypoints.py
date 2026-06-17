from __future__ import annotations

import ast
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
INGEST_ORCHESTRATOR = ROOT / "src" / "orchestrators" / "ingest_orchestrator.py"
GENERATION_WORKFLOW = (
    ROOT / "src" / "orchestrators" / "_report_generation_orchestrator" / "workflow.py"
)
README = ROOT / "README.md"


def _tree(path: Path) -> ast.Module:
    return ast.parse(path.read_text(encoding="utf-8"), filename=str(path))


def _imported_modules(path: Path) -> set[str]:
    imported: set[str] = set()
    for node in ast.walk(_tree(path)):
        if isinstance(node, ast.Import):
            imported.update(alias.name for alias in node.names)
        elif isinstance(node, ast.ImportFrom) and node.module:
            imported.add(node.module)
    return imported


def _call_keyword_names(path: Path, function_name: str) -> set[str]:
    names: set[str] = set()
    for node in ast.walk(_tree(path)):
        if not isinstance(node, ast.Call):
            continue
        func = node.func
        if isinstance(func, ast.Name) and func.id == function_name:
            names.update(keyword.arg or "" for keyword in node.keywords)
    return names


def test_ingest_routes_reports_through_canonical_pipeline_entrypoint() -> None:
    imports = _imported_modules(INGEST_ORCHESTRATOR)

    assert "src.orchestrators.report_pipeline_orchestrator" in imports
    assert "src.orchestrators.report_generation_orchestrator" not in imports
    assert "generate_report_fn" not in _call_keyword_names(
        INGEST_ORCHESTRATOR,
        "run_report_pipeline_orchestrator",
    )


def test_report_generation_routes_analysis_through_stage_entrypoint() -> None:
    imports = _imported_modules(GENERATION_WORKFLOW)

    assert "src.orchestrators.report_analysis_orchestrator" in imports
    assert callable(
        importlib.import_module(
            "src.orchestrators.report_generation_orchestrator"
        ).run_report_generation
    )
    assert callable(
        importlib.import_module(
            "src.orchestrators.report_analysis_orchestrator"
        ).run_report_analysis
    )


def test_readme_documents_report_pipeline_entrypoints() -> None:
    text = README.read_text(encoding="utf-8")

    expected_fragments = [
        "Canonical report workflow entrypoint",
        "`src/orchestrators/ingest_orchestrator.py::run_ingest`",
        "`src/orchestrators/ingest_file_orchestrator.py::run_ingest_file`",
        "`src/orchestrators/report_pipeline_orchestrator.py::run_report_pipeline`",
        "`src/orchestrators/report_generation_orchestrator.py::run_report_generation`",
        "`src/orchestrators/report_analysis_orchestrator.py::run_report_analysis`",
        '`resume_from_stage="analysis_complete"`',
    ]

    for fragment in expected_fragments:
        assert fragment in text
