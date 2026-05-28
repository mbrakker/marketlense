from __future__ import annotations

import ast
import importlib
from pathlib import Path


FACADE = Path("src/generators/publisher_inventory_candidate_screening_generator.py")
PACKAGE = Path("src/generators/_publisher_inventory_candidate_screening")

SHARED_SYMBOLS = {
    "logger",
    "_MAX_PROMPT_TITLE_LENGTH",
    "_FALLBACK_REPORT_TITLE_MARKERS",
    "_FALLBACK_SPECIFIC_REPORT_TITLE_MARKERS",
    "_FALLBACK_NON_REPORT_TITLE_MARKERS",
    "_FALLBACK_NON_REPORT_URL_MARKERS",
    "_FALLBACK_REPORT_URL_MARKERS",
    "_FALLBACK_REPORT_COLLECTION_SEGMENTS",
    "_FALLBACK_LISTING_QUERY_KEYS",
    "_EDITORIAL_REPORT_URL_MARKERS",
    "_COLLECTION_ROOT_URL_TOKENS",
    "_REPORT_CONTEXT_STOP_WORDS",
    "_DIRECT_DETAIL_SOURCE_URL_MARKERS",
    "_EDITORIAL_NON_REPORT_URL_MARKERS",
    "_INFORMATIONAL_TITLE_PREFIXES",
    "_GENERIC_CTA_TITLES",
    "_EDITORIAL_SPECIFIC_REPORT_TITLE_MARKERS",
    "_GENERIC_DUPLICATE_TITLE_FINGERPRINTS",
    "_PUBLISHER_SUCCESS_ANALYST_MARKERS",
    "_PUBLISHER_SUCCESS_HARD_PATTERNS",
    "_normalize_title_fingerprint",
    "_contains_any_title_marker",
    "_normalize_marker_word",
    "_publisher_reference_tokens",
    "_truncate_prompt_text",
}

DETERMINISTIC_SYMBOLS = {
    "_TARGET_MAX_SCREENING_BATCHES",
    "_MAX_DYNAMIC_SCREENING_BATCH_SIZE",
    "_partition_candidates_for_llm_screening",
    "_resolve_candidate_screening_batch_size",
    "_fallback_screening_decision",
    "_is_probable_report_asset",
    "_prefilter_screening_decision",
    "_has_strong_report_detail_url",
    "_has_report_archive_context",
    "_looks_like_human_archive_title",
    "_has_pdf_report_signal",
    "_has_editorial_report_detail_candidate",
    "_looks_like_collection_root_candidate_url",
    "_has_contextual_report_term",
    "_looks_like_confident_direct_detail_source",
    "_is_generic_cta_title",
    "_looks_like_insights_detail_url",
    "_has_specific_editorial_report_slug",
}

RESPONSE_SYMBOLS = {
    "_merge_screening_batches",
    "_coerce_screening_decision_map",
    "_build_screening_response",
    "_deduplicate_screening_response",
    "_apply_publisher_success_hard_rejections",
    "_candidate_duplicate_key",
    "_candidate_selection_key",
    "_is_generic_duplicate_title",
    "_is_publisher_success_marketing_title",
    "_merge_screening_responses_with_prefilter",
}

LLM_SYMBOLS = {
    "_MISSING_DECISION_REPAIR_BATCH_SIZE",
    "_screen_candidate_batch",
    "_chunk_candidates",
}

PUBLIC_SYMBOLS = {"screen_publisher_inventory_candidates"}
ALL_MOVED_SYMBOLS = (
    SHARED_SYMBOLS | DETERMINISTIC_SYMBOLS | RESPONSE_SYMBOLS | LLM_SYMBOLS
)
ALL_COMPATIBILITY_SYMBOLS = ALL_MOVED_SYMBOLS | PUBLIC_SYMBOLS

ALLOWED_SIBLING_IMPORTS = {
    "shared.py": set(),
    "deterministic.py": {"shared"},
    "response_policy.py": {"shared"},
    "llm_batches.py": {"shared", "response_policy", "deterministic"},
}


def _owned_symbols(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    owned: set[str] = set()
    for node in tree.body:
        if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef)):
            owned.add(node.name)
        elif isinstance(node, ast.Assign):
            for target in node.targets:
                if isinstance(target, ast.Name):
                    owned.add(target.id)
        elif isinstance(node, ast.AnnAssign) and isinstance(node.target, ast.Name):
            owned.add(node.target.id)
    return owned


def _imported_siblings(path: Path) -> set[str]:
    tree = ast.parse(path.read_text(encoding="utf-8"), filename=str(path))
    imports: set[str] = set()
    for node in ast.walk(tree):
        if not isinstance(node, ast.ImportFrom):
            continue
        module = node.module or ""
        prefix = "src.generators._publisher_inventory_candidate_screening."
        if module.startswith(prefix):
            imports.add(module.removeprefix(prefix).split(".", 1)[0])
        elif node.level == 1 and module:
            imports.add(module.split(".", 1)[0])
    return imports & {path[:-3] for path in ALLOWED_SIBLING_IMPORTS}


def test_publisher_inventory_candidate_screening_uses_private_modules() -> None:
    assert PACKAGE.joinpath("__init__.py").is_file()
    assert PACKAGE.joinpath("shared.py").is_file()
    assert PACKAGE.joinpath("deterministic.py").is_file()
    assert PACKAGE.joinpath("response_policy.py").is_file()
    assert PACKAGE.joinpath("llm_batches.py").is_file()

    facade_owned = _owned_symbols(FACADE)
    assert PUBLIC_SYMBOLS <= facade_owned
    assert facade_owned.isdisjoint(ALL_MOVED_SYMBOLS)

    assert SHARED_SYMBOLS <= _owned_symbols(PACKAGE / "shared.py")
    assert DETERMINISTIC_SYMBOLS <= _owned_symbols(PACKAGE / "deterministic.py")
    assert RESPONSE_SYMBOLS <= _owned_symbols(PACKAGE / "response_policy.py")
    assert LLM_SYMBOLS <= _owned_symbols(PACKAGE / "llm_batches.py")


def test_publisher_inventory_candidate_screening_facade_preserves_imports() -> None:
    facade = importlib.import_module(
        "src.generators.publisher_inventory_candidate_screening_generator"
    )

    for symbol in ALL_COMPATIBILITY_SYMBOLS:
        assert hasattr(facade, symbol), symbol

    namespace: dict[str, object] = {}
    exec(
        "from src.generators.publisher_inventory_candidate_screening_generator import *",
        namespace,
    )
    assert "screen_publisher_inventory_candidates" in namespace


def test_publisher_inventory_candidate_screening_dependency_direction() -> None:
    for relative_path, allowed in ALLOWED_SIBLING_IMPORTS.items():
        assert _imported_siblings(PACKAGE / relative_path) <= allowed
