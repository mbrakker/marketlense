from __future__ import annotations

import ast
import importlib
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PUBLIC_MODULE_PATH = (
    ROOT / "src" / "orchestrators" / "publisher_inventory_orchestrator.py"
)
PACKAGE = ROOT / "src" / "orchestrators" / "_publisher_inventory_orchestrator"

DEPENDENCY_SYMBOLS = {
    "PublisherInventoryDependencies",
}

IDEMPOTENCY_SYMBOLS = {
    "_RUN_QUALITY_IDEMPOTENCY_SCOPE",
    "_RECOVERY_CACHE_IDEMPOTENCY_SCOPE",
    "_SNAPSHOT_UPLOAD_IDEMPOTENCY_SCOPE",
    "_REPORT_SOURCE_RECORD_IDEMPOTENCY_SCOPE",
    "_STATE_RECORD_IDEMPOTENCY_SCOPE",
    "_TEST_STATUS_IDEMPOTENCY_SCOPE",
    "_lookup_idempotency_record",
    "_record_idempotency_outcome",
    "_idempotency_key_with_checksum",
    "_optional_dataclass_payload",
    "_run_quality_record_checksum",
    "_state_record_checksum",
    "_test_status_record_checksum",
    "_recovery_cache_record_checksum",
    "_record_run_quality_if_needed",
    "_record_state_if_needed",
    "_record_test_status_if_needed",
    "_record_recovery_cache_if_needed",
    "_restore_drive_file",
    "_payload_optional_str",
    "_restore_upload_bytes_response",
    "_restore_report_source_record",
}

SNAPSHOT_SYMBOLS = {
    "_SNAPSHOT_PREFIX",
    "_SNAPSHOT_LOOKBACK_LIMIT",
    "_load_previous_snapshot",
    "_snapshot_file_name",
}

CANDIDATE_FLOW_SYMBOLS = {
    "_rank_qualified_items_by_resource_quality",
    "_candidate_provenance_counts",
    "_record_deferred_candidate_recovery_cache",
    "_log_rollout_guardrails",
    "_source_domain_for_url",
}

RUNTIME_SYMBOLS = {
    "_record_discovery_test_status_on_failure",
    "_discovery_test_status_for_error_code",
    "_run_discovery_attempt",
    "_remaining_time_budget_seconds",
    "_assert_time_budget_remaining",
    "_settings_with_time_budget",
}

SNAPSHOT_RECORD_SYMBOLS = {
    "_upload_snapshot_if_changed",
    "_record_qualified_report_sources",
}

PUBLIC_COORDINATOR_SYMBOLS = {
    "run_publisher_inventory_discovery",
}

ALL_MOVED_SYMBOLS = (
    DEPENDENCY_SYMBOLS
    | IDEMPOTENCY_SYMBOLS
    | SNAPSHOT_SYMBOLS
    | CANDIDATE_FLOW_SYMBOLS
    | RUNTIME_SYMBOLS
    | SNAPSHOT_RECORD_SYMBOLS
)
ALL_PUBLIC_SYMBOLS = ALL_MOVED_SYMBOLS | PUBLIC_COORDINATOR_SYMBOLS


def _owned_symbols(path: Path) -> set[str]:
    module = ast.parse(path.read_text(encoding="utf-8"))
    symbols: set[str] = set()
    for node in module.body:
        if isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            symbols.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    symbols.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            symbols.add(node.target.id)
    return symbols


def test_publisher_inventory_orchestrator_owner_modules_exist() -> None:
    assert (PACKAGE / "dependencies.py").is_file()
    assert (PACKAGE / "idempotency.py").is_file()
    assert (PACKAGE / "snapshot_io.py").is_file()
    assert (PACKAGE / "candidate_flow.py").is_file()
    assert (PACKAGE / "runtime.py").is_file()
    assert (PACKAGE / "snapshot_records.py").is_file()


def test_publisher_inventory_orchestrator_symbols_have_semantic_owners() -> None:
    public_symbols = _owned_symbols(PUBLIC_MODULE_PATH)
    dependency_symbols = _owned_symbols(PACKAGE / "dependencies.py")
    idempotency_symbols = _owned_symbols(PACKAGE / "idempotency.py")
    snapshot_symbols = _owned_symbols(PACKAGE / "snapshot_io.py")
    candidate_flow_symbols = _owned_symbols(PACKAGE / "candidate_flow.py")
    runtime_symbols = _owned_symbols(PACKAGE / "runtime.py")
    snapshot_record_symbols = _owned_symbols(PACKAGE / "snapshot_records.py")

    assert DEPENDENCY_SYMBOLS <= dependency_symbols
    assert IDEMPOTENCY_SYMBOLS <= idempotency_symbols
    assert SNAPSHOT_SYMBOLS <= snapshot_symbols
    assert CANDIDATE_FLOW_SYMBOLS <= candidate_flow_symbols
    assert RUNTIME_SYMBOLS <= runtime_symbols
    assert SNAPSHOT_RECORD_SYMBOLS <= snapshot_record_symbols
    assert PUBLIC_COORDINATOR_SYMBOLS <= public_symbols

    assert not (ALL_MOVED_SYMBOLS & public_symbols)
    assert dependency_symbols & ALL_PUBLIC_SYMBOLS == DEPENDENCY_SYMBOLS
    assert idempotency_symbols & ALL_PUBLIC_SYMBOLS == IDEMPOTENCY_SYMBOLS
    assert snapshot_symbols & ALL_PUBLIC_SYMBOLS == SNAPSHOT_SYMBOLS
    assert candidate_flow_symbols & ALL_PUBLIC_SYMBOLS == CANDIDATE_FLOW_SYMBOLS
    assert runtime_symbols & ALL_PUBLIC_SYMBOLS == RUNTIME_SYMBOLS
    assert snapshot_record_symbols & ALL_PUBLIC_SYMBOLS == SNAPSHOT_RECORD_SYMBOLS
    assert public_symbols & ALL_PUBLIC_SYMBOLS == PUBLIC_COORDINATOR_SYMBOLS


def test_publisher_inventory_orchestrator_compatibility_exports_remain() -> None:
    facade = importlib.import_module(
        "src.orchestrators.publisher_inventory_orchestrator"
    )

    for symbol in ALL_PUBLIC_SYMBOLS:
        assert hasattr(facade, symbol), symbol
