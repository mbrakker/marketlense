from __future__ import annotations

import ast
from pathlib import Path


CAPABILITY_FUNCTIONS = {
    "candidate_readiness.py": {
        "assert_candidate_download_ready",
        "evaluate_candidate_download_readiness",
    },
    "failure_forensics.py": {
        "persist_failed_attempt_forensics_pack",
        "with_failure_forensics_context",
    },
    "promotions.py": {
        "evaluate_route_playbook_promotion",
        "evaluate_private_api_playbook_auto_promotion",
    },
    "persistence.py": {
        "record_route_outcome",
        "record_downloaded_source",
        "record_identity_update",
    },
    "drive_archive.py": {
        "archive_successful_report_artifacts",
        "archive_single_artifact",
    },
}


def _function_names(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_report_download_workflow_delegates_focused_capabilities() -> None:
    package = Path("src/orchestrators/_report_download_orchestrator")
    coordinator_functions = _function_names(package / "workflow.py")

    assert "run_report_download" in coordinator_functions
    for module_name, expected in CAPABILITY_FUNCTIONS.items():
        owned = _function_names(package / module_name)
        assert expected <= owned
        assert not expected & coordinator_functions
