from __future__ import annotations

import ast
import importlib
from pathlib import Path


PACKAGE = Path("src/services/_pdf/_crop")
FACADE = Path("src/services/_pdf/crop.py")
FACADE_MODULE = "src.services._pdf.crop"
MODULE_SYMBOLS = {
    "image_ops.py": {
        "PDF_CROP_EXCEPTIONS",
        "PREVIEW_RENDER_EXCEPTIONS",
        "_dominant_border_color",
        "_row_is_bg",
        "_col_is_bg",
        "_trim_uniform_border",
        "_uniform_border_trim_amounts",
        "_stack_crop_images",
        "_render_clip_image",
    },
    "geometry.py": {
        "_chart_has_internal_top_band",
        "_chart_has_bottom_edge_text",
        "_legacy_chart_border_trim",
        "_expand_chart_top_to_nearby_fill_rect",
        "_heading_is_internal_draw_backed_card_text",
        "_tighten_crop_rect_for_strict_mode",
        "_tighten_chart_crop_rect",
        "_tighten_table_crop_rect",
        "_crop_refine_text_blocks",
        "_crop_refine_edge_guard_rect",
    },
    "table_continuation.py": {
        "_TableContinuationAugment",
        "_normalize_block_text",
        "_block_lines",
        "_text_starts_with_explicit_table_title",
        "_text_has_note_marker",
        "_page_text_blocks",
        "_find_explicit_table_title_block",
        "_table_title_strip_rect",
        "_table_note_strip_rect",
        "_table_header_tokens",
        "_is_wide_table_continuation_region",
        "_build_table_continuation_augments",
    },
    "regions.py": {
        "_ResolvedCropRegion",
        "_crop_output_filename",
        "crop_regions",
        "_crop_regions",
    },
    "refine.py": {
        "render_page_for_crop_refine",
        "apply_crop_refine_bbox",
    },
    "preview.py": {
        "render_preview",
        "_page_png",
    },
}
COMPATIBILITY_SYMBOLS = set().union(*MODULE_SYMBOLS.values())
ALLOWED_SIBLING_IMPORTS = {
    "image_ops.py": set(),
    "geometry.py": {"image_ops"},
    "table_continuation.py": {"image_ops"},
    "regions.py": {"image_ops", "geometry", "table_continuation"},
    "refine.py": {"image_ops", "geometry"},
    "preview.py": {"image_ops"},
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


def _sibling_imports(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if isinstance(node, ast.ImportFrom) and node.module:
            parts = node.module.split(".")
            if "_crop" in parts:
                imports.add(parts[-1])
        elif isinstance(node, ast.ImportFrom) and node.level == 1:
            if node.module:
                imports.add(node.module.split(".")[-1])
    return imports & set(ALLOWED_SIBLING_IMPORTS)


def test_pdf_crop_uses_focused_private_capability_modules() -> None:
    facade_symbols = _owned_symbols(FACADE)

    for relative_path, expected in MODULE_SYMBOLS.items():
        owned = _owned_symbols(PACKAGE / relative_path)
        assert expected <= owned
        assert not expected & facade_symbols


def test_pdf_crop_preserves_compatibility_surface() -> None:
    facade = importlib.import_module(FACADE_MODULE)

    for symbol in COMPATIBILITY_SYMBOLS:
        assert hasattr(facade, symbol)
        assert symbol in facade.__all__


def test_pdf_crop_private_modules_keep_acyclic_dependency_direction() -> None:
    for relative_path, allowed in ALLOWED_SIBLING_IMPORTS.items():
        assert _sibling_imports(PACKAGE / relative_path) <= allowed
