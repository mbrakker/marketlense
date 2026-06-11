from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_FACADE_LINES = 1_000

TARGET_FACADES = (
    "src/contracts/cross_report_analysis.py",
    "src/services/_pdf/_table_heuristics/screening.py",
    "src/services/_pdf/_table_heuristics/regions.py",
    "src/services/_browser_report_download/_browser_runtime/session_lifecycle.py",
    "src/services/_report_store_service/download_routes.py",
)

EXPECTED_OWNER_SYMBOLS = {
    "src/contracts/_cross_report_analysis/requests.py": {
        "CrossReportAnalysisRequest",
        "CrossReportAnalysisOrchestratorRequest",
        "CrossReportProjectedDataReadRequest",
    },
    "src/contracts/_cross_report_analysis/selection.py": {
        "CrossReportThemeCandidate",
        "CrossReportSourceSelectionResult",
        "CrossReportEvidenceInputResult",
    },
    "src/contracts/_cross_report_analysis/publication.py": {
        "CrossReportPublishPackage",
        "CrossReportPublishResultSummary",
    },
    "src/contracts/_cross_report_analysis/validation.py": {
        "validate_cross_report_contract",
    },
    "src/services/_pdf/_table_heuristics/_screening/rejections.py": {
        "_validate_table_candidate",
        "_contents_like",
        "_reference_block_like",
    },
    "src/services/_pdf/_table_heuristics/_screening/deduplication.py": {
        "_dedupe_table_candidates",
        "_TableDedupeSpatialIndex",
    },
    "src/services/_pdf/_table_heuristics/_regions/ranked.py": {
        "_detect_ranked_table_candidates",
        "_ranked_table_panel_region",
    },
    "src/services/_pdf/_table_heuristics/_regions/compose.py": {
        "_compose_table_bbox",
        "_expand_table_bbox",
    },
    "src/services/_browser_report_download/_browser_runtime/_session_lifecycle/history.py": {
        "_run_agent_history_with_timeout",
        "_read_completed_agent_history",
    },
    "src/services/_browser_report_download/_browser_runtime/_session_lifecycle/partial_history.py": {
        "_read_email_domain_blocker_partial_history",
        "_read_lookup_blocker_partial_history",
    },
    "src/services/_browser_report_download/_browser_runtime/_session_lifecycle/cleanup.py": {
        "_cleanup_stale_browser_use_temp_dirs",
        "_cleanup_new_browser_use_temp_dirs",
    },
    "src/services/_browser_report_download/_browser_runtime/_session_lifecycle/shutdown.py": {
        "_prepare_browser_for_shutdown",
        "_kill_browser_with_timeout",
    },
    "src/services/_report_store_service/_download_routes/private_api.py": {
        "record_publisher_private_api_candidate_observation",
        "mark_publisher_private_api_candidate_promoted",
    },
    "src/services/_report_store_service/_download_routes/route_lookup.py": {
        "get_publisher_download_route",
    },
    "src/services/_report_store_service/_download_routes/route_recording.py": {
        "record_publisher_download_route",
    },
}


def _line_count(relative_path: str) -> int:
    return len((ROOT / relative_path).read_text(encoding="utf-8").splitlines())


def _owned_symbols(relative_path: str) -> set[str]:
    path = ROOT / relative_path
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


def test_requested_runtime_files_have_semantic_private_owners() -> None:
    too_long = {
        relative_path: _line_count(relative_path)
        for relative_path in TARGET_FACADES
        if _line_count(relative_path) > MAX_FACADE_LINES
    }

    assert too_long == {}
    for relative_path, expected_symbols in EXPECTED_OWNER_SYMBOLS.items():
        assert (ROOT / relative_path).is_file(), relative_path
        assert expected_symbols <= _owned_symbols(relative_path)
