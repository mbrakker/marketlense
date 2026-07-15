from __future__ import annotations

import ast
from pathlib import Path


CLI_PATH = Path("src/cli.py")
CLI_PACKAGE = Path("src/_cli")


EXPECTED_OWNERS = {
    "app.py": {"cli_app", "cli", "main"},
    "common.py": {"_default_log_path"},
    "cross_report.py": {
        "_build_cross_report_cli_request",
        "generate_cross_report_analysis_cli",
    },
    "private_api.py": {
        "_load_private_api_promotion_request",
        "promote_private_api_playbook",
    },
    "trace.py": {"_load_structured_log_events", "_trace_depths", "trace_run"},
    "pipeline.py": {
        "ingest",
        "extract_candidates",
        "publish_wp",
        "recategorize",
        "generate_covers",
        "update_wp_categories",
        "cost_report",
    },
    "browser.py": {"download_report", "browser_doctor"},
    "publisher.py": {"discover_publisher_inventory", "audit_acquisition_paths"},
    "admin.py": {"drive_oauth_login", "sync_publishers"},
    "claim_embedding.py": {
        "embedding_queue_health",
        "embedding_queue_reconcile",
        "embedding_queue_run",
        "embedding_queue_failures",
    },
    "ui_runs.py": {"replay_run", "ui_run_worker"},
}


def _module_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"))
    symbols: set[str] = set()
    for node in tree.body:
        if isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.add(target.id)
        elif isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
    return symbols


def test_cli_facade_stays_below_monolithic_threshold() -> None:
    line_count = len(CLI_PATH.read_text(encoding="utf-8").splitlines())

    assert line_count < 1000


def test_cli_command_families_have_private_owners() -> None:
    missing_modules = [
        module_name
        for module_name in EXPECTED_OWNERS
        if not (CLI_PACKAGE / module_name).exists()
    ]

    assert missing_modules == []

    for module_name, expected_symbols in EXPECTED_OWNERS.items():
        module_symbols = _module_symbols(CLI_PACKAGE / module_name)
        assert expected_symbols <= module_symbols
