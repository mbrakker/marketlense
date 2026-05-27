from __future__ import annotations

import ast
import importlib
from pathlib import Path


PACKAGE = Path("src/services/_pdf/_visual_candidates")
FACADE = Path("src/services/_pdf/visual_candidates.py")
FACADE_MODULE = "src.services._pdf.visual_candidates"
MODULE_SYMBOLS = {
    "raster.py": {
        "_RasterProbeCache",
        "_has_side_by_side_visual_sibling",
        "_render_visual_probe_image",
        "_visual_probe_profile",
        "_embedded_visual_looks_chart_like",
        "_bounded_quality",
        "_candidate_ocr_density",
        "_chart_confidence_score",
        "_embedded_visual_looks_decorative",
        "_embedded_visual_looks_photo_like",
        "_embedded_visual_is_oversized_wrapper",
        "_embedded_visual_qualifies_relaxed_geometry",
        "_left_side_context_signal",
        "_embedded_visual_qualifies_contextual_card",
    },
    "screening.py": {
        "_iter_visual_context_lines",
        "_page_has_chart_caption_blocks",
        "_text_has_visual_context_hint",
        "_visual_nonempty_lines",
        "_caption_has_figure_hint",
        "_caption_looks_explanatory_figure_reference",
        "_caption_looks_bare_title_heading",
        "_caption_looks_mid_sentence_fragment",
        "_visual_candidate_looks_table_like",
        "_visual_candidate_looks_note_fragment",
        "_visual_candidate_looks_bare_heading_fragment",
        "_visual_candidate_looks_reference_or_prose",
        "_visual_candidate_looks_cover_art",
        "_visual_candidate_looks_section_opener_banner",
        "_visual_candidate_looks_photo_narrative_card",
        "_visual_candidate_looks_narrative_panel_card",
        "_visual_candidate_looks_inline_numbered_panel",
        "_next_figure_caption_below",
        "_visual_text_dense_recovery_allowed",
    },
    "extraction.py": {
        "_VisualPageContext",
        "_VisualPageCandidateEntry",
        "_initial_visual_stats",
        "_build_visual_page_context",
        "_append_visual_page_candidate",
        "_emit_visual_page_candidates",
        "_extract_visuals_sequential",
        "extract_visual_candidates",
    },
}
COMPATIBILITY_SYMBOLS = set().union(*MODULE_SYMBOLS.values())


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


def test_pdf_visual_candidates_use_focused_private_capability_modules() -> None:
    facade_symbols = _owned_symbols(FACADE)

    for relative_path, expected in MODULE_SYMBOLS.items():
        owned = _owned_symbols(PACKAGE / relative_path)
        assert expected <= owned
        assert not expected & facade_symbols


def test_pdf_visual_candidates_preserve_compatibility_surface() -> None:
    facade = importlib.import_module(FACADE_MODULE)

    for symbol in COMPATIBILITY_SYMBOLS:
        assert hasattr(facade, symbol)
        assert symbol in facade.__all__


def test_pdf_visual_candidates_facade_imports_owners_in_dependency_order() -> None:
    tree = ast.parse(FACADE.read_text(encoding="utf-8"), filename=str(FACADE))
    owners = [
        node.module
        for node in tree.body
        if isinstance(node, ast.ImportFrom)
        and node.module is not None
        and "_visual_candidates" in node.module
    ]
    assert owners == [
        "_visual_candidates.raster",
        "_visual_candidates.screening",
        "_visual_candidates.extraction",
    ]
