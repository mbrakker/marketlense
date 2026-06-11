from __future__ import annotations

import ast
from pathlib import Path


CAPABILITY_MODULE_FUNCTIONS = {
    "terminal_state.py": {
        "_capture_terminal_snapshot",
        "_stabilize_terminal_snapshot",
        "_assess_terminal_snapshot_quorum",
    },
    "_terminal_assets/artifacts.py": {
        "_materialize_external_artifacts",
    },
    "_terminal_assets/capture.py": {
        "_capture_terminal_assets",
    },
    "_terminal_assets/network.py": {
        "_collect_network_events",
    },
    "timeout_recovery.py": {
        "_salvage_timed_out_browser_run",
        "_attempt_lookup_submission_assist_with_timeout",
    },
    "worker_protocol.py": {
        "_run_browser_report_download_agent_subprocess",
        "_deserialize_browser_agent_run_result",
    },
    "_session_lifecycle/history.py": {
        "_run_agent_history_with_timeout",
    },
    "_session_lifecycle/shutdown.py": {
        "_prepare_browser_for_shutdown",
        "_kill_browser",
    },
    "_session_lifecycle/cleanup.py": {
        "_cleanup_stale_browser_use_temp_dirs",
    },
}


def _top_level_functions(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    return {
        node.name
        for node in tree.body
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef))
    }


def test_browser_runtime_uses_focused_private_capability_modules() -> None:
    package_dir = Path("src/services/_browser_report_download/_browser_runtime")
    coordinator_functions = _top_level_functions(
        Path("src/services/_browser_report_download/browser.py")
    )

    assert package_dir.joinpath("__init__.py").is_file()
    for file_name, owned_functions in CAPABILITY_MODULE_FUNCTIONS.items():
        module_path = package_dir / file_name
        assert module_path.is_file()
        assert owned_functions <= _top_level_functions(module_path)
        assert coordinator_functions.isdisjoint(owned_functions)
