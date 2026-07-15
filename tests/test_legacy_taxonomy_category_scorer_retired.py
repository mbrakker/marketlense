from __future__ import annotations

import importlib.util
from pathlib import Path

import yaml

import src.contracts.categories as category_contracts


def test_legacy_taxonomy_category_scorer_surface_is_removed() -> None:
    repo_root = Path(__file__).resolve().parents[1]

    assert not (repo_root / "src" / "generators" / "categorize_generator.py").exists()
    assert not (repo_root / "tests" / "test_categorize_generator.py").exists()
    assert importlib.util.find_spec("src.generators.categorize_generator") is None
    assert not hasattr(category_contracts, "CategoryClassificationConfig")
    assert not hasattr(category_contracts, "CategoryScoreDetail")


def test_category_mapping_config_no_longer_exposes_scoring_policy() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    mapping_path = repo_root / "src" / "config" / "category-mappings.yaml"
    payload = yaml.safe_load(mapping_path.read_text(encoding="utf-8"))

    assert "classification" not in payload
    for category in payload.get("categories") or []:
        assert "tags" not in category


def test_editorial_output_documents_context_first_categories() -> None:
    repo_root = Path(__file__).resolve().parents[1]
    readme_text = (repo_root / "docs" / "product" / "editorial-output.md").read_text(
        encoding="utf-8"
    )

    assert "legacy weighted tag-mapping" not in readme_text
    assert (
        "taxonomy tags are weighted against the scoring signal groups"
        not in readme_text
    )
    assert "Before category scoring" not in readme_text
    assert "Context-first category assignment" in readme_text
