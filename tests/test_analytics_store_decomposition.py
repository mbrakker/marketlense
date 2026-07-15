from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "services" / "_analytics_store"
FACADE = ROOT / "src" / "services" / "analytics_store_service.py"

COMMON = {
    "DEFAULT_BUSY_TIMEOUT_SECONDS",
    "_CONN_LOCK",
    "_EMBEDDING_STATUSES",
    "_CROSS_REPORT_READ_CONTENT_CLASSES",
    "DDL",
    "_REPORT_PROJECTION_COLUMNS",
    "_analytics_conn",
    "_configure",
    "_ensure_reports_projection_columns",
    "_json",
    "_lineage_values",
    "_uid_set",
}

PROJECTION_WRITE = {
    "_report_source_url_from_store",
    "_delete_stale",
    "_upsert_report",
    "_upsert_sections",
    "_upsert_findings",
    "_upsert_metrics",
    "_upsert_quotes",
    "_upsert_claims",
    "_upsert_tags",
    "_upsert_categories",
    "_upsert_figures",
    "_validate_queue_row",
    "_upsert_vector_queue",
    "upsert_projection",
    "record_projection_failure",
}

CROSS_REPORT_READ = {
    "_normalized_filter_values",
    "_status_floor_values",
    "_json_list",
    "_fetch_grouped_rows",
    "_fetch_vector_hashes",
    "_aggregate_content_hash",
    "_report_period",
    "_report_date",
    "_row_text",
    "_report_publisher",
    "_stable_row_id",
    "_scoped_row_id",
    "_report_passes_filters",
    "_source_candidate",
    "_claim_evidence",
    "_finding_evidence",
    "_quote_evidence",
    "_raw_metric",
    "_requested_content_classes",
    "read_cross_report_projected_data",
}

CLAIM_EMBEDDINGS = {
    "_embedding_uid",
    "claim_embedding_uid",
    "_metadata_from_json",
    "_queue_item_from_row",
    "_record_from_row",
    "read_pending_claim_embedding_rows",
    "_validate_embedding_record",
    "persist_claim_embedding",
    "_matches_topics",
    "read_claim_embeddings",
}

QUEUE_REMEDIATION = {
    "acquire_claim_embedding_execution_lease",
    "read_claim_embedding_queue_health",
    "reconcile_claim_embedding_queue",
}

SIGNALS = {
    "_candidate_source_ref_from_dict",
    "_candidate_from_row",
    "_group_from_row",
    "_delete_stale_signal_rows",
    "_upsert_signal_group",
    "_upsert_signal_candidate",
    "upsert_signal_candidates",
    "_candidate_matches_read_request",
    "read_signal_candidates",
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


def test_analytics_store_owner_modules_exist() -> None:
    for name in (
        "common.py",
        "projection_write.py",
        "cross_report_read.py",
        "claim_embeddings.py",
        "queue_remediation.py",
        "signals.py",
    ):
        assert (PACKAGE / name).is_file()


def test_analytics_store_symbols_have_one_owner() -> None:
    expected = {
        "common.py": COMMON,
        "projection_write.py": PROJECTION_WRITE,
        "cross_report_read.py": CROSS_REPORT_READ,
        "claim_embeddings.py": CLAIM_EMBEDDINGS,
        "queue_remediation.py": QUEUE_REMEDIATION,
        "signals.py": SIGNALS,
    }
    all_expected = set().union(*expected.values())
    for filename, symbols in expected.items():
        assert _owned(PACKAGE / filename) & all_expected == symbols


def test_analytics_store_facade_import_order() -> None:
    imports = [
        node.module.rsplit(".", 1)[-1]
        for node in ast.parse(FACADE.read_text(encoding="utf-8")).body
        if isinstance(node, ast.ImportFrom)
        and node.module
        and "._analytics_store." in node.module
    ]
    assert imports == [
        "common",
        "projection_write",
        "cross_report_read",
        "claim_embeddings",
        "queue_remediation",
        "signals",
    ]


def test_projection_writer_batches_multirow_upserts() -> None:
    source = (PACKAGE / "projection_write.py").read_text(encoding="utf-8")

    for function_name in (
        "_upsert_sections",
        "_upsert_findings",
        "_upsert_metrics",
        "_upsert_quotes",
        "_upsert_claims",
        "_upsert_tags",
        "_upsert_categories",
        "_upsert_figures",
        "_upsert_vector_queue",
    ):
        function_source = source.split(f"def {function_name}", 1)[1].split("\ndef ", 1)[
            0
        ]
        assert ".executemany(" in function_source
        assert ".execute(" not in function_source
