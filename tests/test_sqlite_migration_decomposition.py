from __future__ import annotations

import ast
import importlib
from pathlib import Path


PACKAGE = Path("src/services/_sqlite_migration")
FACADE = Path("src/services/sqlite_migration_service.py")
FACADE_MODULE = "src.services.sqlite_migration_service"
MODULE_SYMBOLS = {
    "runner.py": {
        "_MigrationSpec",
        "_add_column_if_missing",
        "_applied_migration_ids",
        "_apply_migration_plan",
        "_current_version",
        "_fetch_columns",
        "_normalize_url_key",
    },
    "reports.py": {
        "_REPORTS_DB_MIGRATIONS",
        "_reports_db_003_normalize_report_sources",
        "_reports_db_005_normalize_publishers",
        "_reports_db_006_create_or_upgrade_download_route_history",
        "_reports_db_007_normalize_inventory_recovery_cache",
        "_reports_db_013_create_signal_candidate_projection",
        "_reports_db_014_create_claim_embedding_records",
    },
    "state.py": {
        "_STATE_DB_MIGRATIONS",
        "_state_db_001_create_base_tables",
        "_state_db_005_add_report_download_final_page_url",
    },
    "ui_runs.py": {
        "_UI_RUN_REGISTRY_MIGRATIONS",
        "_ui_run_registry_001_create_ui_runs",
        "_ui_run_registry_002_add_dead_letter_ledger",
    },
}
COMPATIBILITY_SYMBOLS = {
    "_REPORTS_DB_MIGRATIONS",
    "_STATE_DB_MIGRATIONS",
    "_UI_RUN_REGISTRY_MIGRATIONS",
    "apply_reports_db_migrations",
    "apply_state_db_migrations",
    "apply_ui_run_registry_migrations",
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


def test_sqlite_migration_uses_database_family_owner_modules() -> None:
    facade_symbols = _owned_symbols(FACADE)
    for relative_path, expected in MODULE_SYMBOLS.items():
        owner_path = PACKAGE / relative_path
        owned = _owned_symbols(owner_path)
        if relative_path == "reports.py":
            owned |= set().union(
                *(_owned_symbols(path) for path in (PACKAGE / "_reports").glob("*.py"))
            )
        assert expected <= owned
        assert not expected & facade_symbols


def test_sqlite_migration_preserves_compatibility_surface() -> None:
    facade = importlib.import_module(FACADE_MODULE)
    for symbol in COMPATIBILITY_SYMBOLS:
        assert hasattr(facade, symbol)


def test_sqlite_migration_facade_imports_owners_in_dependency_order() -> None:
    tree = ast.parse(FACADE.read_text(encoding="utf-8"), filename=str(FACADE))
    owners = [
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and "_sqlite_migration" in node.module
    ]
    assert owners == [
        "_sqlite_migration.runner",
        "_sqlite_migration.reports",
        "_sqlite_migration.state",
        "_sqlite_migration.ui_runs",
    ]
