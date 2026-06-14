from __future__ import annotations

import ast
import importlib
from pathlib import Path


PACKAGE = Path("src/services/_pdf/_visual_heuristics")
COORDINATOR = PACKAGE / "panel_detection.py"
DETECTION_PACKAGE = PACKAGE / "_panel_detection"
FACADE_MODULE = "src.services._pdf.visual_heuristics"
MODULE_SYMBOLS = {
    "panel_text.py": {
        "_panel_title_lines",
        "_panel_lowercase_title_has_metric_context",
        "_panel_local_title_line",
        "_panel_preferred_local_title_line",
        "_panel_titles_form_multiline_band",
        "_shared_row_panel_title_line",
        "_panel_title_slice_bounds",
        "_panel_chart_is_label_dense_not_prose",
        "_numeric_token_hits",
        "_panel_chart_has_metric_signal",
        "_panel_label_block_looks_like_footer_banner",
        "_panel_chart_has_data_signal",
        "_panel_component_text_from_blocks",
        "_panel_component_has_chart_signal",
        "_panel_component_looks_like_independent_data_panel",
        "_panel_component_looks_like_guidance_card",
        "_panel_chart_has_structured_card_signal",
        "_panel_caption_looks_like_compact_metric",
        "_panel_chart_has_compact_stat_card_signal",
        "_panel_caption_looks_top_band",
    },
    "panel_geometry.py": {
        "_extend_panel_rect_with_nearby_label_blocks",
        "_drawing_components",
        "_shared_title_component_group",
        "_stacked_panel_group_has_intervening_text",
        "_extend_panel_rect_with_adjacent_drawings",
        "_clamp_panel_rect_to_dominant_fill_rect",
        "_extend_panel_with_adjacent_text_blocks",
    },
    "_panel_detection/shadowing.py": {
        "_panel_should_clamp_to_internal_caption",
        "_panel_candidate_shadowed_by_heading_candidate",
        "_panel_candidate_shadowed_by_larger_panel",
        "_panel_stacked_bottom_clip_y",
        "_panel_neighbor_x_bounds",
    },
    "_panel_detection/candidates.py": {
        "_page_looks_like_contents_layout",
        "_panel_chart_rects",
        "_merge_panel_title_band_candidates",
    },
}
COMPATIBILITY_FACADE_SYMBOLS = {
    "_panel_should_clamp_to_internal_caption",
    "_panel_candidate_shadowed_by_heading_candidate",
    "_panel_candidate_shadowed_by_larger_panel",
    "_panel_stacked_bottom_clip_y",
    "_panel_neighbor_x_bounds",
    "_page_looks_like_contents_layout",
    "_panel_chart_rects",
    "_merge_panel_title_band_candidates",
}
COMPATIBILITY_SYMBOLS = set().union(*MODULE_SYMBOLS.values())
TYPE_DECLARATION_OWNER = PACKAGE / "type_declarations.py"
TYPE_DECLARATION_CONSUMERS = (
    PACKAGE / "panel_text.py",
    PACKAGE / "panel_geometry.py",
    DETECTION_PACKAGE / "shadowing.py",
    DETECTION_PACKAGE / "candidates.py",
)
SHARED_TYPE_HELPERS = {
    "_ChartRect",
    "_PageTextLine",
    "_VisualCandidateRelationships",
    "_alpha_ratio",
    "_horizontal_overlap_ratio",
    "_is_page_number_text",
    "_line_starts_with_caption_hint",
    "_rect_containment_ratio",
    "_rect_iou",
    "_rect_overlap_area",
    "_rect_seen",
    "_s",
    "_starts_with_lower_alpha",
    "_table_normalize_text",
    "_table_page_text_lines",
    "_text_stats",
    "_vertical_overlap_ratio",
    "_drawing_rects",
    "_caption_blocks",
    "_compact_top_chart_title_like",
    "_chart_axis_label_band_like",
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


def test_pdf_panel_detection_uses_focused_private_capability_modules() -> None:
    coordinator_symbols = _owned_symbols(COORDINATOR)
    assert not COMPATIBILITY_FACADE_SYMBOLS & coordinator_symbols

    for relative_path, expected in MODULE_SYMBOLS.items():
        owned = _owned_symbols(PACKAGE / relative_path)
        assert expected <= owned
        assert not expected & coordinator_symbols


def test_pdf_panel_detection_preserves_visual_heuristic_compatibility_surface() -> None:
    facade = importlib.import_module(FACADE_MODULE)

    for symbol in COMPATIBILITY_SYMBOLS:
        assert hasattr(facade, symbol)
        assert symbol in facade.__all__


def test_pdf_panel_type_helpers_have_one_private_declaration_owner() -> None:
    owner_symbols = _owned_symbols(TYPE_DECLARATION_OWNER)
    assert SHARED_TYPE_HELPERS <= owner_symbols

    for consumer in TYPE_DECLARATION_CONSUMERS:
        assert not SHARED_TYPE_HELPERS & _owned_symbols(consumer)
