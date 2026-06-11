from __future__ import annotations

import ast
from pathlib import Path


CAPABILITY_MODULE_FUNCTIONS = {
    "pdf.py": {"_complete_pdf_artifact", "_resolve_downloaded_file"},
    "onsite.py": {
        "_ensure_onsite_capture_artifact",
        "_infer_onsite_completeness_status",
    },
    "_classification/evidence.py": {"_resolve_blocked_reason"},
    "_classification/workflow.py": {"_classify_route_result"},
    "evidence.py": {"_build_terminal_evidence", "_verify_post_action_route_steps"},
    "recovery.py": {
        "_salvage_without_structured_result",
        "_recover_from_invalid_artifact",
    },
}


def _top_level_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_artifact_finalization_uses_focused_private_capability_modules() -> None:
    package_dir = Path("src/services/_browser_report_download/_artifact")
    coordinator_functions = _top_level_functions(
        Path("src/services/_browser_report_download/artifact.py")
    )

    assert package_dir.joinpath("__init__.py").is_file()
    for file_name, owned_functions in CAPABILITY_MODULE_FUNCTIONS.items():
        module_path = package_dir / file_name
        assert module_path.is_file()
        assert owned_functions <= _top_level_functions(module_path)
        assert coordinator_functions.isdisjoint(owned_functions)
