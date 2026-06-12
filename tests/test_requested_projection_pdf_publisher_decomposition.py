from __future__ import annotations

import ast
from pathlib import Path


ROOT = Path(__file__).resolve().parents[1]
MAX_FACADE_LINES = 1_000

TARGET_FACADES = (
    "src/generators/analytics_projection_generator.py",
    "src/generators/_report_selection_generator/crop_refine.py",
    "src/services/_pdf/_visual_heuristics/panel_detection.py",
    "src/services/_publisher_inventory_service/discovery_activity.py",
)

EXPECTED_OWNER_SYMBOLS = {
    "src/generators/_analytics_projection/builders.py": {
        "_build_sections",
        "_build_findings",
        "_build_metrics",
        "_build_quotes",
        "_build_claims",
        "_build_tags",
        "_build_categories",
        "_build_figures",
    },
    "src/generators/_analytics_projection/vector_queue.py": {
        "_build_vector_queue",
        "_queue_metadata",
        "_queue_row",
    },
    "src/generators/_analytics_projection/workflow.py": {
        "build_projection",
    },
    "src/generators/_report_selection_generator/_crop_refine/cache.py": {
        "_crop_refine_profile_key",
        "_crop_refine_entry_key",
        "_load_crop_refine_cache",
        "_write_crop_refine_cache",
    },
    "src/generators/_report_selection_generator/_crop_refine/workflow.py": {
        "select_refined_candidate_items",
    },
    "src/services/_pdf/_visual_heuristics/_panel_detection/shadowing.py": {
        "_panel_should_clamp_to_internal_caption",
        "_panel_candidate_shadowed_by_heading_candidate",
        "_panel_candidate_shadowed_by_larger_panel",
        "_panel_stacked_bottom_clip_y",
        "_panel_neighbor_x_bounds",
    },
    "src/services/_pdf/_visual_heuristics/_panel_detection/candidates.py": {
        "_panel_chart_rects",
        "_merge_panel_title_band_candidates",
    },
    "src/services/_publisher_inventory_service/_discovery_activity/candidates.py": {
        "_resolve_next_page_url",
        "_extract_candidates_from_html",
        "_extract_component_link_anchors",
        "_looks_like_report_candidate",
    },
    "src/services/_publisher_inventory_service/_discovery_activity/browser_state.py": {
        "_should_follow_report_listing",
        "_should_expand_archive_library",
        "_is_exhausted_inert_load_more",
        "_build_browser_route_summary",
    },
    "src/services/_publisher_inventory_service/_discovery_activity/urls.py": {
        "_normalize_absolute_url",
        "_looks_like_report_listing_route_url",
        "_is_same_inventory_domain",
    },
    "src/services/_publisher_inventory_service/_discovery_activity/titles.py": {
        "_select_anchor_title",
        "_fallback_title_from_url",
        "_normalize_text",
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


def test_requested_projection_pdf_publisher_files_have_private_owners() -> None:
    too_long = {
        relative_path: _line_count(relative_path)
        for relative_path in TARGET_FACADES
        if _line_count(relative_path) > MAX_FACADE_LINES
    }

    assert too_long == {}
    for relative_path, expected_symbols in EXPECTED_OWNER_SYMBOLS.items():
        assert (ROOT / relative_path).is_file(), relative_path
        assert expected_symbols <= _owned_symbols(relative_path)
