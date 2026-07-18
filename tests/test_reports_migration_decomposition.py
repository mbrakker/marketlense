from __future__ import annotations

import ast
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "services" / "_sqlite_migration" / "_reports"
FACADE = PACKAGE.parent / "reports.py"

SCHEMA = {
    "_REPORTS_CORE_TABLE_SQL",
    "_REPORTS_REQUIRED_COLUMNS",
    "_REPORT_SOURCES_TABLE_SQL",
    "_PUBLISHERS_TABLE_SQL",
    "_DOWNLOAD_ROUTE_HISTORY_TABLE_SQL",
    "_PRIVATE_API_CANDIDATE_TABLE_SQL",
    "_INVENTORY_RECOVERY_CACHE_TABLE_SQL",
    "_INVENTORY_ROUTE_HISTORY_TABLE_SQL",
    "_REPORT_SECTIONS_TABLE_SQL",
    "_REPORT_FINDINGS_TABLE_SQL",
    "_REPORT_METRICS_TABLE_SQL",
    "_REPORT_QUOTES_TABLE_SQL",
    "_REPORT_CLAIMS_TABLE_SQL",
    "_REPORT_TAGS_TABLE_SQL",
    "_REPORT_CATEGORIES_TABLE_SQL",
    "_REPORT_FIGURES_TABLE_SQL",
    "_VECTOR_PROJECTION_QUEUE_TABLE_SQL",
    "_CLAIM_EMBEDDINGS_TABLE_SQL",
    "_CLAIM_EMBEDDING_QUEUE_TRANSITIONS_TABLE_SQL",
    "_SIGNAL_CANDIDATES_TABLE_SQL",
    "_SIGNAL_CANDIDATE_GROUPS_TABLE_SQL",
    "_ARTIFACT_EXECUTION_PLAN_RUNS_TABLE_SQL",
    "_SOURCE_PUBLICATION_METADATA_TABLE_SQL",
}

CORE = {
    "_reports_db_001_create_reports_core",
    "_reports_db_002_create_report_sources_base",
    "_reports_db_003_normalize_report_sources",
    "_reports_db_004_create_publishers_base",
    "_reports_db_005_normalize_publishers",
}

ROUTING = {
    "_reports_db_006_create_or_upgrade_download_route_history",
    "_reports_db_007_normalize_inventory_recovery_cache",
    "_reports_db_008_create_inventory_route_history",
    "_reports_db_012_create_private_api_candidate_ledger",
}

PROJECTIONS = {
    "_reports_db_009_add_reports_projection_columns",
    "_reports_db_010_create_analytics_projection_tables",
    "_reports_db_011_add_report_source_value_scores",
    "_reports_db_013_create_signal_candidate_projection",
    "_reports_db_014_create_claim_embedding_records",
    "_reports_db_015_create_artifact_lineage_registry",
    "_reports_db_016_add_claim_embedding_queue_controls",
    "_reports_db_017_add_lineage_execution_planning",
    "_reports_db_018_create_source_publication_metadata",
    "_reports_db_019_create_source_identity_observations",
    "_reports_db_020_expand_execution_plan_audit",
}


def _owned(path: Path) -> set[str]:
    symbols: set[str] = set()
    for node in ast.parse(path.read_text(encoding="utf-8")).body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            symbols.update(
                target.id for target in node.targets if isinstance(target, ast.Name)
            )
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            symbols.add(node.target.id)
    return symbols


def test_reports_migration_owner_modules_exist() -> None:
    for name in ("schema.py", "core.py", "routing.py", "projections.py"):
        assert (PACKAGE / name).is_file()


def test_reports_migration_symbols_have_one_owner() -> None:
    expected = {
        "schema.py": SCHEMA,
        "core.py": CORE,
        "routing.py": ROUTING,
        "projections.py": PROJECTIONS,
    }
    all_expected = set().union(*expected.values())
    for filename, symbols in expected.items():
        assert _owned(PACKAGE / filename) & all_expected == symbols


def test_reports_migration_facade_owns_ordered_registry_only() -> None:
    owned = _owned(FACADE)
    assert owned & (SCHEMA | CORE | ROUTING | PROJECTIONS) == set()
    assert "_REPORTS_DB_MIGRATIONS" in owned
