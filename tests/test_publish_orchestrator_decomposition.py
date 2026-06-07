from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
PACKAGE = ROOT / "src" / "orchestrators" / "_publish_orchestrator"
FACADE = PACKAGE.parent / "publish_orchestrator.py"

MODELS = {
    "_PUBLISH_IDEMPOTENCY_SCOPE",
    "_CROSS_REPORT_PUBLISH_IDEMPOTENCY_SCOPE",
    "_PublishEntityRoute",
    "_PUBLISH_ENTITY_ROUTES",
    "_PUBLISH_ROUTES_BY_INTENT",
    "_CROSS_REPORT_WORDPRESS_POST_TYPES",
    "_PublishCandidate",
    "_PublishPreflightEntry",
    "_CrossReportWordPressClassification",
    "_CrossReportResultFields",
}

ROUTING = {
    "_metadata_index",
    "_sort_auto_discovered_html_paths",
    "_publish_settings_for_post_type",
    "_require_publish_settings",
    "_publish_entity_error",
    "_route_publish_entity_metadata",
    "_resolve_publish_candidates",
    "_normalize_string_list",
    "_normalize_tag_slugs",
}

PREFLIGHT = {
    "_batch_lookup_existing_posts",
    "_resolve_batch_term_assignments",
    "_build_publish_preflight_entries",
    "_validation_paths",
    "_load_validation_report",
    "_with_validation",
}

IDEMPOTENCY = {
    "_publish_idempotency_key",
    "_publish_checksum",
    "_lookup_publish_idempotency",
    "_record_publish_idempotency",
    "_cross_report_publish_checksum",
    "_cross_report_publish_idempotency_key",
    "_record_cross_report_publish_idempotency",
    "_lookup_cross_report_publish_idempotency",
}

CROSS_REPORT = {
    "_cross_report_post_type_for_target_route",
    "_cross_report_settings_for_target_route",
    "_unique_terms_from_labels",
    "_cross_report_publisher_labels",
    "_cross_report_wordpress_classification",
    "_publish_entity_metadata_for_route",
    "_cross_report_result_fields",
    "_resolve_cross_report_terms",
    "_briefing_url_is_in_section",
    "_signal_url_is_in_section",
    "_cross_report_result_from_outcome",
    "_signal_projection_package",
}

PUBLIC = {"run_publish", "publish_cross_report_package", "publish_signal_projection"}


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


def test_publish_orchestrator_owner_modules_exist() -> None:
    for name in (
        "models.py",
        "routing.py",
        "preflight.py",
        "idempotency.py",
        "cross_report.py",
    ):
        assert (PACKAGE / name).is_file()


def test_publish_orchestrator_symbols_have_one_owner() -> None:
    expected = {
        "models.py": MODELS,
        "routing.py": ROUTING,
        "preflight.py": PREFLIGHT,
        "idempotency.py": IDEMPOTENCY,
        "cross_report.py": CROSS_REPORT,
    }
    all_expected = set().union(*expected.values())
    for filename, symbols in expected.items():
        assert _owned(PACKAGE / filename) & all_expected == symbols


def test_publish_orchestrator_public_entrypoints_remain_in_facade() -> None:
    assert _owned(FACADE) & PUBLIC == PUBLIC
